import calendar
import sqlite3
from datetime import date, timedelta
from email.message import EmailMessage
from functools import wraps
from locale import LC_ALL, setlocale
from smtplib import SMTP_SSL
from uuid import uuid4

from flask import (
    Flask, Markup, abort, flash, g, redirect, render_template, request,
    session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

setlocale(LC_ALL, 'fr_FR')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='paillette.db')
app.config.from_envvar('PAILLETTE_CONFIG', silent=True)


def get_connection():
    if not hasattr(g, 'connection'):
        g.connection = sqlite3.connect(
            app.config['DB'], detect_types=sqlite3.PARSE_DECLTYPES)
        g.connection.execute('PRAGMA foreign_keys')
        g.connection.row_factory = sqlite3.Row
    return g.connection


def close_connection():
    if hasattr(g, 'connection'):
        g.connection.close()


def get_person_from_id(person_id):
    cursor = get_connection().cursor()
    cursor.execute(
        'SELECT *, person.firstname || " " || person.lastname AS name '
        'FROM person WHERE id = (?)',
        (person_id,))
    return cursor.fetchone()


def get_person():
    if 'person_id' not in session:
        return None
    if not hasattr(g, 'person'):
        g.person = get_person_from_id(session['person_id'])
    return g.person


def get_date_data(year, month):
    if None in (year, month):
        today = date.today()
        year, month = today.year, today.month
    start = date(year, month, 1)
    stop = date(year, month, calendar.monthrange(year, month)[1])
    previous = start - timedelta(days=1)
    next = stop + timedelta(days=1)
    return year, month, start, stop, previous, next


def authenticated(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if get_person():
            return function(*args, **kwargs)
        return abort(403)
    return wrapper


# Common
@app.route('/')
def index():
    return redirect(url_for('spectacles' if get_person() else 'login'))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        cursor.execute(
            'SELECT id, password FROM person WHERE mail = :login',
            request.form)
        person = cursor.fetchone()
        if person and (app.config['DEBUG'] or person['password']):
            passwords = person['password'], request.form['password']
            if app.config['DEBUG'] or check_password_hash(*passwords):
                session['person_id'] = person['id']
                return redirect(url_for('index'))
        flash('L’identifiant ou le mot de passe est incorrect.')
        return redirect(url_for('login'))
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    session.pop('person_id', None)
    return redirect(url_for('login'))


@app.route('/password/lost', methods=('GET', 'POST'))
def password_lost():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        uuid = str(uuid4())
        mail = request.form['mail']
        cursor.execute('''
            UPDATE person
            SET reset_password = ?
            WHERE mail = ?
            RETURNING id, firstname, lastname
        ''', (uuid, mail))
        person = cursor.fetchone()
        cursor.connection.commit()
        if person:
            url = url_for("password_reset", uuid=uuid, _external=True)
            if app.config['DEBUG']:
                flash(Markup(f'<a href="{url}">Nouveau mot de passe</a>.'))
                return redirect(url_for('login'))
            smtp = SMTP_SSL(app.config['SMTP_HOSTNAME'])
            smtp.login(app.config['SMTP_LOGIN'], app.config['SMTP_PASSWORD'])
            message = EmailMessage()
            message['From'] = app.config['SMTP_FROM']
            message['To'] = request.form['mail']
            message['Subject'] = 'Réinitialisation de mot de passe'
            message.set_content(
                f'Bonjour {person["firstname"]} {person["lastname"]},\n\n'
                'Vous avez demandé une réinitialisation de mot de passe '
                'concernant votre compte Paillette. Merci de vous rendre '
                'sur l’adresse suivante pour changer votre mot de passe :\n\n'
                f'{url}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, vous pouvez '
                'ignorer ce message.'
            )
            smtp.send_message(message)
            smtp.quit()
        elif app.config['DEBUG']:
            flash(f'Aucun utilisateur avec l’adresse {mail}.')
            return redirect(url_for('login'))
        flash('Un message vous a été envoyé si votre email est correct.')
        return redirect(url_for('login'))
    return render_template('password_lost.jinja2.html')


@app.route('/password/reset/<uuid>', methods=('GET', 'POST'))
def password_reset(uuid):
    cursor = get_connection().cursor()
    if request.method == 'POST':
        password_match = (
            request.form.get('password') ==
            request.form.get('confirm_password'))
        if not password_match:
            flash('Les deux mots de passe doivent être les mêmes.')
            return redirect(request.referrer)
        cursor.execute('''
            UPDATE person
            SET password = ?, reset_password = NULL
            WHERE reset_password = ?
        ''', (generate_password_hash(request.form['password']), uuid))
        cursor.connection.commit()
        flash('Le mot de passe a été modifié, merci de vous connecter.')
        return redirect(url_for('login'))
    return render_template('password_reset.jinja2.html')


@app.route('/<type>/<int:id>/hide', methods=('GET', 'POST'))
@authenticated
def hide(type, id):
    if type not in ('vehicle', 'makeup', 'sound', 'artist', 'costume'):
        return abort(404)

    cursor = get_connection().cursor()
    if request.method == 'POST':
        cursor.execute(f'UPDATE {type} SET hidden = TRUE WHERE id = ?', (id,))
        cursor.connection.commit()
        flash('L’élément a été caché.')
        return redirect(url_for(f'{type}s'))

    if type == 'artist':
        cursor.execute('''
            SELECT person.firstname || " " || person.lastname AS name
            FROM person
            JOIN artist
            ON person.id = artist.person_id
            WHERE artist.id = ?
        ''', (id,))
    else:
        cursor.execute(f'SELECT * FROM {type} WHERE id = ?', (id,))
    element = cursor.fetchone()
    return render_template('hide.jinja2.html', element=element)


@app.route('/<type>/<int:id>/show', methods=('GET', 'POST'))
@authenticated
def show(type, id):
    if type not in ('vehicle', 'makeup', 'sound', 'artist', 'costume'):
        return abort(404)

    cursor = get_connection().cursor()
    if request.method == 'POST':
        cursor.execute(f'UPDATE {type} SET hidden = FALSE WHERE id = ?', (id,))
        cursor.connection.commit()
        flash('L’élément a été caché.')
        return redirect(url_for(f'{type}s'))

    if type == 'artist':
        cursor.execute('''
            SELECT person.firstname || " " || person.lastname AS name
            FROM person
            JOIN artist
            ON person.id = artist.person_id
            WHERE artist.id = ?
        ''', (id,))
    else:
        cursor.execute(f'SELECT * FROM {type} WHERE id = ?', (id,))
    element = cursor.fetchone()
    return render_template('show.jinja2.html', element=element)


# Spectacles
@app.route('/spectacles')
@app.route('/spectacles/<int:year>/<int:month>')
@authenticated
def spectacles(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT *
        FROM spectacle
        WHERE date_from BETWEEN ? AND ?
        OR date_to BETWEEN ? AND ?
        ORDER BY date_from
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    spectacles = cursor.fetchall()
    return render_template(
        'spectacles.jinja2.html', spectacles=spectacles, start=start,
        stop=stop, previous=previous, next=next)


@app.route('/spectacle/create', methods=('GET', 'POST'))
@authenticated
def spectacle_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        parameters['trigram'] = parameters['place'][:3].upper()
        cursor.execute('''
            INSERT INTO
              spectacle (
                event, place, travel_time, trigram, date_from, date_to)
            VALUES
              (:event, :place, :travel_time, :trigram, :date_from, :date_to)
            RETURNING
              id
        ''', parameters)
        spectacle_id = cursor.fetchone()['id']
        cursor.connection.commit()
        flash('Le spectacle a été ajouté.')
        return redirect(url_for('spectacle', spectacle_id=spectacle_id))
    return render_template('spectacle_create.jinja2.html')


@app.route('/spectacle/<int:spectacle_id>')
@authenticated
def spectacle(spectacle_id):
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          spectacle.*,
          representation.name AS representation_name,
          representation_date.date AS representation_date
        FROM spectacle
        LEFT JOIN representation
        ON spectacle.id = representation.spectacle_id
        LEFT JOIN representation_date
        ON representation.id = representation_date.id
        WHERE spectacle.id = ?
        ORDER BY representation_name, representation_date
    ''', (spectacle_id,))
    representation_dates = cursor.fetchall()
    return render_template(
        'spectacle.jinja2.html', representation_dates=representation_dates)


@app.route('/spectacle/<int:spectacle_id>/update', methods=('GET', 'POST'))
@authenticated
def spectacle_update(spectacle_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = spectacle_id
        cursor.execute('''
            UPDATE spectacle
            SET
              date_from = :date_from,
              date_to = :date_to,
              event = :event,
              travel_time = :travel_time,
              trigram = :trigram
            WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('spectacle', spectacle_id=spectacle_id))

    cursor.execute('''
        SELECT
          spectacle.*,
          representation.name AS representation_name,
          representation_date.date AS representation_date
        FROM spectacle
        LEFT JOIN representation
        ON spectacle.id = representation.spectacle_id
        LEFT JOIN representation_date
        ON representation.id = representation_date.id
        WHERE spectacle.id = ?
        ORDER BY representation_name, representation_date
    ''', (spectacle_id,))
    representation_dates = cursor.fetchall()
    return render_template(
        'spectacle_update.jinja2.html',
        representation_dates=representation_dates)


# Roadmaps
@app.route('/roadmap/<int:spectacle_id>')
@authenticated
def roadmap(spectacle_id):
    return render_template('roadmap.jinja2.html')


@app.route('/roadmap/send')
def roadmap_send():
    return render_template('roadmap_send.jinja2.html')


# Follow-ups
@app.route('/artists/followup')
@app.route('/artists/followup/<int:year>/<int:month>')
@authenticated
def artists_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    artists_spectacles = []
    return render_template(
        'artists_followup.jinja2.html',
        artists_spectacles=artists_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/costumes/followup')
@app.route('/costumes/followup/<int:year>/<int:month>')
@authenticated
def costumes_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          costume.id AS costume_id,
          costume.name,
          spectacle.trigram,
          spectacle.date_from,
          spectacle.date_to
        FROM costume
        LEFT JOIN costume_spectacle
        ON costume.id = costume_spectacle.costume_id
        LEFT JOIN (
          SELECT *
          FROM spectacle
          WHERE (date_from IS NULL AND date_to IS NULL)
          OR date_from BETWEEN ? AND ?
          OR date_to BETWEEN ? AND ?
        ) AS spectacle
        ON costume_spectacle.spectacle_id = spectacle.id
        ORDER BY name
      ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    costumes_spectacles = cursor.fetchall()
    return render_template(
        'costumes_followup.jinja2.html',
        costumes_spectacles=costumes_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/makeups/followup')
@app.route('/makeups/followup/<int:year>/<int:month>')
@authenticated
def makeups_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          makeup.id AS makeup_id,
          makeup.name,
          spectacle.trigram,
          spectacle.date_from,
          spectacle.date_to
        FROM makeup
        LEFT JOIN makeup_spectacle
        ON makeup.id = makeup_spectacle.makeup_id
        LEFT JOIN (
          SELECT *
          FROM spectacle
          WHERE (date_from IS NULL AND date_to IS NULL)
          OR date_from BETWEEN ? AND ?
          OR date_to BETWEEN ? AND ?
        ) AS spectacle
        ON makeup_spectacle.spectacle_id = spectacle.id
        ORDER BY name
      ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    makeups_spectacles = cursor.fetchall()
    return render_template(
        'makeups_followup.jinja2.html',
        makeups_spectacles=makeups_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/sounds/followup')
@app.route('/sounds/followup/<int:year>/<int:month>')
@authenticated
def sounds_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          sound.id AS sound_id,
          sound.name,
          spectacle.trigram,
          spectacle.date_from,
          spectacle.date_to
        FROM sound
        LEFT JOIN sound_spectacle
        ON sound.id = sound_spectacle.sound_id
        LEFT JOIN (
          SELECT *
          FROM spectacle
          WHERE (date_from IS NULL AND date_to IS NULL)
          OR date_from BETWEEN ? AND ?
          OR date_to BETWEEN ? AND ?
        ) AS spectacle
        ON sound_spectacle.spectacle_id = spectacle.id
        ORDER BY name
      ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    sounds_spectacles = cursor.fetchall()
    return render_template(
        'sounds_followup.jinja2.html',
        sounds_spectacles=sounds_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/vehicles/followup')
@app.route('/vehicles/followup/<int:year>/<int:month>')
@authenticated
def vehicles_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          vehicle.id AS vehicle_id,
          vehicle.name,
          spectacle.trigram,
          spectacle.date_from,
          spectacle.date_to
        FROM vehicle
        LEFT JOIN vehicle_spectacle
        ON vehicle.id = vehicle_spectacle.vehicle_id
        LEFT JOIN (
          SELECT *
          FROM spectacle
          WHERE (date_from IS NULL AND date_to IS NULL)
          OR date_from BETWEEN ? AND ?
          OR date_to BETWEEN ? AND ?
        ) AS spectacle
        ON vehicle_spectacle.spectacle_id = spectacle.id
        ORDER BY name
      ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    vehicles_spectacles = cursor.fetchall()
    return render_template(
        'vehicles_followup.jinja2.html',
        vehicles_spectacles=vehicles_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/availabilities/update')
def availabilities_update():
    return render_template('availabilities_update.jinja2.html')


# Persons
@app.route('/person/update', methods=('GET', 'POST'))
@app.route('/person/<int:person_id>/update', methods=('GET', 'POST'))
@authenticated
def person_update(person_id=None):
    person = g.person if person_id is None else get_person_from_id(person_id)

    if request.method == 'POST':
        password_match = (
            request.form.get('password') ==
            request.form.get('confirm_password'))
        if not password_match:
            flash('Les deux mots de passe doivent être les mêmes.')
            return redirect(url_for('person_update', person_id=person_id))

        cursor = get_connection().cursor()
        parameters = dict(request.form)
        parameters['id'] = person['id']
        cursor.execute('''
            UPDATE person
            SET
              mail = :mail,
              firstname = :firstname,
              lastname = :lastname,
              phone = :phone
            WHERE id = :id
        ''', parameters)
        if (password := request.form.get('password')):
            cursor.execute(
                'UPDATE person SET password = ? WHERE id = ?',
                (generate_password_hash(password), person['id']))
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('person_update', person_id=person_id))

    return render_template('person_update.jinja2.html', person=person)


@app.route('/persons')
@authenticated
def persons():
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        person.*,
        person.firstname || " " || person.lastname AS name
      FROM person
      LEFT JOIN artist
      ON person.id = artist.person_id
      WHERE artist.id IS NULL
      ORDER BY name
    ''')
    persons = cursor.fetchall()
    return render_template('persons.jinja2.html', persons=persons)


@app.route('/person/create', methods=('GET', 'POST'))
@authenticated
def person_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
            INSERT INTO person (firstname, lastname, mail, phone)
            VALUES (:firstname, :lastname, :mail, :phone)
        ''', parameters)
        cursor.connection.commit()
        flash('La personne a été ajoutée.')
        return redirect(url_for('persons'))
    return render_template('person_create.jinja2.html')


# Costumes
@app.route('/costumes')
@authenticated
def costumes():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM costume ORDER BY name')
    costumes = cursor.fetchall()
    return render_template('costumes.jinja2.html', costumes=costumes)


@app.route('/costume/<int:costume_id>/update', methods=('GET', 'POST'))
@authenticated
def costume_update(costume_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = costume_id
        cursor.execute('''
            UPDATE costume
            SET
              name = :name,
              color = :color
            WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('costumes'))

    cursor.execute('SELECT * FROM costume WHERE id = ?', (costume_id,))
    costume = cursor.fetchone()
    return render_template('costume_update.jinja2.html', costume=costume)


@app.route('/costume/create', methods=('GET', 'POST'))
@authenticated
def costume_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
            INSERT INTO costume (name, color)
            VALUES (:name, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('Le costume a été créée.')
        return redirect(url_for('costumes'))

    return render_template('costume_create.jinja2.html')


# Make-ups
@app.route('/makeups')
@authenticated
def makeups():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM makeup ORDER BY name')
    makeups = cursor.fetchall()
    return render_template('makeups.jinja2.html', makeups=makeups)


@app.route('/makeup/<int:makeup_id>/update', methods=('GET', 'POST'))
@authenticated
def makeup_update(makeup_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = makeup_id
        cursor.execute('''
            UPDATE makeup
            SET
              name = :name,
              color = :color
            WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('makeups'))

    cursor.execute('SELECT * FROM makeup WHERE id = ?', (makeup_id,))
    makeup = cursor.fetchone()
    return render_template('makeup_update.jinja2.html', makeup=makeup)


@app.route('/makeup/create', methods=('GET', 'POST'))
@authenticated
def makeup_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
            INSERT INTO makeup (name, color)
            VALUES (:name, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('La boîte à maquillage a été créée.')
        return redirect(url_for('makeups'))

    return render_template('makeup_create.jinja2.html')


# Sounds
@app.route('/sounds')
@authenticated
def sounds():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM sound ORDER BY name')
    sounds = cursor.fetchall()
    return render_template('sounds.jinja2.html', sounds=sounds)


@app.route('/sound/<int:sound_id>/update', methods=('GET', 'POST'))
@authenticated
def sound_update(sound_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = sound_id
        cursor.execute('''
            UPDATE sound
            SET
              name = :name,
              color = :color
            WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('sounds'))

    cursor.execute('SELECT * FROM sound WHERE id = ?', (sound_id,))
    sound = cursor.fetchone()
    return render_template('sound_update.jinja2.html', sound=sound)


@app.route('/sound/create', methods=('GET', 'POST'))
@authenticated
def sound_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
            INSERT INTO sound (name, color)
            VALUES (:name, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('Le matériel de son a été créée.')
        return redirect(url_for('sounds'))

    return render_template('sound_create.jinja2.html')


# Vehicles
@app.route('/vehicles')
@authenticated
def vehicles():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM vehicle ORDER BY name')
    vehicles = cursor.fetchall()
    return render_template('vehicles.jinja2.html', vehicles=vehicles)


@app.route('/vehicle/<int:vehicle_id>/update', methods=('GET', 'POST'))
@authenticated
def vehicle_update(vehicle_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = vehicle_id
        parameters['rented'] = parameters['rental_status'] == 'rental'
        cursor.execute('''
            UPDATE vehicle
            SET
              name = :name,
              color = :color,
              type = :type,
              license_plate = :license_plate,
              rented = :rented,
              rental_company_name = :rental_company_name,
              rental_company_hours = :rental_company_hours,
              rental_company_address = :rental_company_address,
              rented_from = :rented_from,
              rented_to = :rented_to
            WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('vehicles'))

    cursor.execute('SELECT * FROM vehicle WHERE id = ?', (vehicle_id,))
    vehicle = cursor.fetchone()
    return render_template('vehicle_update.jinja2.html', vehicle=vehicle)


@app.route('/vehicle/create', methods=('GET', 'POST'))
@authenticated
def vehicle_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        parameters['rented'] = parameters['rental_status'] == 'rental'
        cursor.execute('''
            INSERT INTO
              vehicle (
                name, color, type, license_plate, rented, rental_company_name,
                rental_company_hours, rental_company_address, rented_from,
                rented_to)
            VALUES
              (:name, :color, :type, :license_plate, :rented,
               :rental_company_name, :rental_company_hours,
               :rental_company_address, :rented_from, :rented_to)
        ''', parameters)
        cursor.connection.commit()
        flash('Le véhicule a été créée.')
        return redirect(url_for('vehicles'))

    return render_template('vehicle_create.jinja2.html')


# Artists
@app.route('/artists')
@authenticated
def artists():
    cursor = get_connection().cursor()
    cursor.execute('''
        SELECT
          artist.*,
          person.mail,
          person.firstname,
          person.lastname,
          person.phone,
          person.firstname || " " || person.lastname AS name
        FROM artist
        JOIN person
        ON artist.person_id = person.id
        ORDER BY name
    ''')
    artists = cursor.fetchall()
    return render_template('artists.jinja2.html', artists=artists)


@app.route('/artist/<int:artist_id>/update', methods=('GET', 'POST'))
@authenticated
def artist_update(artist_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = artist_id
        cursor.execute('''
            UPDATE artist
            SET color = :color
            WHERE id = :id
            RETURNING person_id
        ''', parameters)
        parameters['person_id'] = cursor.fetchone()['person_id']
        cursor.execute('''
            UPDATE person
            SET
              mail = :mail,
              firstname = :firstname,
              lastname = :lastname,
              phone = :phone
            WHERE id = :person_id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('artists'))

    cursor.execute('''
        SELECT
          artist.*,
          person.mail,
          person.firstname,
          person.lastname,
          person.phone,
          person.firstname || " " || person.lastname AS name
        FROM artist
        JOIN person
        ON artist.person_id = person.id
        WHERE artist.id = ?
    ''', (artist_id,))
    artist = cursor.fetchone()
    return render_template('artist_update.jinja2.html', artist=artist)


@app.route('/artist/create', methods=('GET', 'POST'))
@authenticated
def artist_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
            INSERT INTO person (mail, firstname, lastname, phone)
            VALUES (:mail, :firstname, :lastname, :phone)
            RETURNING id
        ''', parameters)
        parameters['person_id'] = cursor.fetchone()['id']
        cursor.execute('''
            INSERT INTO artist (person_id, color)
            VALUES (:person_id, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('L’artiste a été ajouté.')
        return redirect(url_for('artists'))

    return render_template('artist_create.jinja2.html')
