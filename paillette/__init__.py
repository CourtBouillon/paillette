import calendar
import sqlite3
from datetime import date, datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from functools import wraps
from locale import LC_ALL, setlocale
from pathlib import Path
from smtplib import SMTP_SSL
from uuid import uuid4

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session,
    url_for)
from flask_weasyprint import HTML, render_pdf
from markupsafe import Markup
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

setlocale(LC_ALL, 'fr_FR.utf8')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='paillette.db',
    SMTP_HOSTNAME=None,
    SMTP_LOGIN=None,
    SMTP_PASSWORD=None,
    SMTP_FROM='sender@example.com',
)
app.config.from_envvar('PAILLETTE_CONFIG', silent=True)


def get_connection():
    if not hasattr(g, 'connection'):
        g.connection = sqlite3.connect(
            app.config['DB'], detect_types=sqlite3.PARSE_DECLTYPES)
        g.connection.row_factory = sqlite3.Row
        cursor = g.connection.cursor()
        cursor.execute('PRAGMA foreign_keys')
        cursor.close()
    return g.connection


def close_connection():
    if hasattr(g, 'connection'):
        g.connection.rollback()
        g.connection.close()


@app.teardown_appcontext
def teardown(exception):
    close_connection()


def get_person_from_id(person_id):
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM person WHERE id = (?)', (person_id,))
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


def get_spectacle_data(spectacle_id):
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        spectacle.*,
        representation.id AS representation_id,
        representation.name AS representation_name,
        GROUP_CONCAT(DISTINCT representation_date.date)
          AS representation_dates,
        GROUP_CONCAT(
          DISTINCT
            replace(person.name, ',', ' ') || '||' ||
            replace(person.phone, ',', ' '))
          AS artists_name_and_phone
      FROM spectacle
      LEFT JOIN representation
      ON spectacle.id = representation.spectacle_id
      LEFT JOIN representation_date
      ON representation.id = representation_date.representation_id
      LEFT JOIN artist_representation_date
      ON
        representation_date.id =
        artist_representation_date.representation_date_id
      LEFT JOIN artist
      ON artist_representation_date.artist_id = artist.id
      LEFT JOIN person
      ON artist.person_id = person.id
      WHERE spectacle.id = ?
      GROUP BY representation.id
      ORDER BY representation_dates
    ''', (spectacle_id,))
    representations = cursor.fetchall()
    cursor.execute('''
      SELECT makeup.*
      FROM makeup
      JOIN makeup_spectacle
      ON makeup.id = makeup_spectacle.makeup_id
      WHERE makeup_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    makeups = cursor.fetchall()
    cursor.execute('''
      SELECT sound.*
      FROM sound
      JOIN sound_spectacle
      ON sound.id = sound_spectacle.sound_id
      WHERE sound_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    sounds = cursor.fetchall()
    cursor.execute('''
      SELECT vehicle.*
      FROM vehicle
      JOIN vehicle_spectacle
      ON vehicle.id = vehicle_spectacle.vehicle_id
      WHERE vehicle_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    vehicles = cursor.fetchall()
    cursor.execute('''
      SELECT costume.*
      FROM costume
      JOIN costume_spectacle
      ON costume.id = costume_spectacle.costume_id
      WHERE costume_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    costumes = cursor.fetchall()
    cursor.execute('''
      SELECT id, filename
      FROM spectacle_image
      WHERE spectacle_id = ?
    ''', (spectacle_id,))
    images = cursor.fetchall()
    return {
        'representations': representations,
        'makups': makeups,
        'sounds': sounds,
        'vehicles': vehicles,
        'costumes': costumes,
        'images': images,
    }


def send_mail(to, subject, content, pdfs=None):
    message = MIMEMultipart()
    message['From'] = app.config['SMTP_FROM']
    for to in to:
        message['To'] = to
    message['Date'] = formatdate(localtime=True)
    message['Subject'] = subject
    message.attach(MIMEText(content))

    for name, pdf in (pdfs or {}).items():
        part = MIMEBase('application', 'pdf')
        part.set_payload(pdf)
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename={secure_filename(name)}')
        message.attach(part)

    if app.config['DEBUG']:
        headers = str(message).split('\n\n', 1)[0]
        markup = (
            '<p>Message envoyé</p>'
            f'<pre>{headers}</pre>'
            f'<pre>{content}</pre>'
        )
        if pdfs:
            markup += f'<p>+ {len(pdfs)} PDF</p>'
        flash(Markup(markup))
        return

    smtp = SMTP_SSL(app.config['SMTP_HOSTNAME'])
    smtp.login(app.config['SMTP_LOGIN'], app.config['SMTP_PASSWORD'])
    smtp.send_message(message)
    smtp.quit()


def authenticated(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if get_person():
            return function(*args, **kwargs)
        return abort(403)
    return wrapper


@app.errorhandler(403)
def page_not_found(error):
    flash('Merci de vous connecter pour accéder à cette page')
    return render_template('login.jinja2.html', redirect=request.path), 403


@app.template_filter('date_range')
def date_range(dates):
    date_from, date_to = dates
    if not all(dates):
        return 'dates indéterminées'
    if isinstance(date_from, str):
        date_from = datetime.fromisoformat(date_from)
    if isinstance(date_to, str):
        date_to = datetime.fromisoformat(date_to)
    if date_from == date_to:
        return f'le {date_simple(date_from)}'
    else:
        return f'du {date_simple(date_from)} au {date_simple(date_to)}'


@app.template_filter('date_simple')
def date_simple(date_or_string):
    if not date_or_string:
        return 'date indéterminée'
    if isinstance(date_or_string, str):
        date_or_string = date.fromisoformat(date_or_string)
    return date_or_string.strftime('%d/%m')


# Common
@app.route('/')
def index():
    return redirect(url_for('spectacles' if get_person() else 'login'))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        redirect_url = request.form.get('redirect')
        cursor = get_connection().cursor()
        cursor.execute('''
          SELECT person.id, password
          FROM person
          WHERE id NOT IN (SELECT person_id FROM artist)
          AND mail IS NOT NULL
          AND mail = :login
        ''', request.form)
        person = cursor.fetchone()
        if person and (app.config['DEBUG'] or person['password']):
            passwords = person['password'], request.form['password']
            if app.config['DEBUG'] or check_password_hash(*passwords):
                session['person_id'] = person['id']
                return redirect(redirect_url or url_for('index'))
        flash('L’identifiant ou le mot de passe est incorrect.')
        return redirect(redirect_url or url_for('login'))
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
          AND mail IS NOT NULL
          AND id NOT IN (SELECT person_id FROM artist)
          RETURNING id, firstname, lastname
        ''', (uuid, mail))
        person = cursor.fetchone()
        cursor.connection.commit()
        if person:
            to = (request.form['mail'],)
            subject = 'Réinitialisation de mot de passe'
            url = url_for('password_reset', uuid=uuid, _external=True)
            content = (
                f'Bonjour {person["firstname"]} {person["lastname"]},\n\n'
                'Vous avez demandé une réinitialisation de mot de passe '
                'concernant votre compte Paillette. Merci de vous rendre '
                'sur l’adresse suivante pour changer votre mot de passe :\n\n'
                f'{url}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, vous pouvez '
                'ignorer ce message.'
            )
            send_mail(to, subject, content)
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
          SELECT name
          FROM person
          JOIN artist
          ON person.id = artist.person_id
          WHERE artist.id = ?
        ''', (id,))
    else:
        cursor.execute(f'SELECT * FROM {type} WHERE id = ?', (id,))
    element = cursor.fetchone() or abort(404)
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
        flash('L’élément n’est plus caché.')
        return redirect(url_for(f'{type}s'))

    if type == 'artist':
        cursor.execute('''
          SELECT name
          FROM person
          JOIN artist
          ON person.id = artist.person_id
          WHERE artist.id = ?
        ''', (id,))
    else:
        cursor.execute(f'SELECT * FROM {type} WHERE id = ?', (id,))
    element = cursor.fetchone() or abort(404)
    return render_template('show.jinja2.html', element=element)


# Spectacles
@app.route('/spectacles')
@app.route('/spectacles/<int:year>/<int:month>')
@authenticated
def spectacles(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        spectacle.*,
        MIN(date) AS first_date,
        MAX(date) AS last_date,
        GROUP_CONCAT(
          DISTINCT replace(representation.name, ',', ' ')) AS representations
      FROM spectacle
      LEFT JOIN representation
      ON spectacle.id = representation.spectacle_id
      LEFT JOIN representation_date
      ON representation.id = representation_date.representation_id
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
      GROUP BY spectacle.id
      ORDER BY date_from
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    spectacles = cursor.fetchall()
    return render_template(
        'spectacles.jinja2.html', spectacles=spectacles, start=start,
        stop=stop, previous=previous, next=next)


@app.route('/spectacle/<int:spectacle_id>')
@authenticated
def spectacle(spectacle_id):
    spectacle_data = get_spectacle_data(spectacle_id)
    return render_template('spectacle.jinja2.html', **spectacle_data)


@app.route('/spectacle/create', methods=('GET', 'POST'))
@authenticated
def spectacle_create():
    tables = ('sound', 'makeup', 'costume', 'vehicle')
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['trigram'] = parameters['place'][:3].upper()
        cursor.execute('''
          INSERT INTO
            spectacle (
              event, place, travel_time, trigram, date_from, date_to, link,
              configuration, organizer, manager)
          VALUES
            (:event, :place, :travel_time, :trigram, :date_from, :date_to,
             :link, :configuration, :organizer, :manager)
          RETURNING id
        ''', parameters)
        spectacle_id = cursor.fetchone()['id']

        for table in tables:
            for table_id in request.form.getlist(f'{table}s'):
                cursor.execute(f'''
                  INSERT INTO
                    {table}_spectacle ({table}_id, spectacle_id)
                  VALUES
                    (?, ?)
                ''', (table_id, spectacle_id))

        for key, name in request.form.items():
            if not key.endswith('-name'):
                continue
            key = key.split('-', 1)[0]
            dates = request.form.getlist(f'{key}-dates')
            artists = set(request.form.getlist(f'{key}-artists'))
            cursor.execute('''
              INSERT INTO representation (spectacle_id, name)
              VALUES (?, ?)
              RETURNING id
            ''', (spectacle_id, name))
            representation_id = cursor.fetchone()['id']
            for representation_date in dates:
                if not representation_date:
                    continue
                cursor.execute('''
                  INSERT INTO representation_date (representation_id, date)
                  VALUES (?, ?)
                  RETURNING id
                ''', (representation_id, representation_date))
                representation_date_id = cursor.fetchone()['id']
                for artist_id in artists:
                    if not artist_id:
                        continue
                    cursor.execute('''
                      INSERT INTO
                        artist_representation_date
                        (representation_date_id, artist_id)
                      VALUES
                        (?, ?)
                    ''', (representation_date_id, artist_id))

        cursor.connection.commit()
        flash('Le spectacle a été ajouté.')
        return redirect(url_for('spectacle', spectacle_id=spectacle_id))

    data = {}
    for table in tables:
        cursor.execute(f'SELECT * FROM {table} WHERE NOT hidden ORDER BY name')
        data[f'{table}s'] = cursor.fetchall()
    cursor.execute('''
      SELECT artist.id, person.name
      FROM artist
      JOIN person
      ON artist.person_id = person.id
      WHERE NOT hidden
      ORDER BY name
    ''')
    all_artists = cursor.fetchall()
    cursor.execute('''
      SELECT DISTINCT manager
      FROM spectacle
      WHERE manager IS NOT NULL
      ORDER BY id DESC LIMIT 100
    ''')
    all_managers = tuple(row['manager'] for row in cursor.fetchall())
    cursor.execute('''
      SELECT DISTINCT name
      FROM representation
      ORDER BY id DESC LIMIT 100
    ''')
    all_representations = tuple(row['name'] for row in cursor.fetchall())
    return render_template(
        'spectacle_create.jinja2.html', all_artists=all_artists,
        all_managers=all_managers, all_representations=all_representations,
        **data)


@app.route('/spectacle/<int:spectacle_id>/update', methods=('GET', 'POST'))
@authenticated
def spectacle_update(spectacle_id):
    tables = ('sound', 'makeup', 'costume', 'vehicle')
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = spectacle_id
        cursor.execute('''
          UPDATE spectacle
          SET
            event = :event,
            place = :place,
            travel_time = :travel_time,
            trigram = :trigram,
            date_from = :date_from,
            date_to = :date_to,
            link = :link,
            configuration = :configuration,
            organizer = :organizer,
            manager = :manager
          WHERE id = :id
        ''', parameters)

        for table in tables:
            cursor.execute(
                f'DELETE FROM {table}_spectacle WHERE spectacle_id = ?',
                (spectacle_id,))
            for table_id in request.form.getlist(f'{table}s'):
                cursor.execute(f'''
                  INSERT INTO {table}_spectacle ({table}_id, spectacle_id)
                  VALUES (?, ?)
                ''', (table_id, spectacle_id))

        cursor.execute('''
          SELECT
            representation.id AS representation_id,
            representation_date.id AS representation_date_id,
            artist_representation_date.id AS artist_representation_date_id
          FROM representation
          LEFT OUTER JOIN representation_date
          ON representation.id = representation_date.representation_id
          LEFT OUTER JOIN artist_representation_date
          ON
            representation_date.id =
            artist_representation_date.representation_date_id
          WHERE
            representation.spectacle_id = ?
        ''', (spectacle_id,))
        rows = cursor.fetchall()
        artist_representation_date_ids = {
            row['artist_representation_date_id'] for row in rows
            if row['artist_representation_date_id']}
        representation_date_ids = {
            row['representation_date_id'] for row in rows
            if row['representation_date_id']}
        representation_ids = {
            row['representation_id'] for row in rows
            if row['representation_id']}
        cursor.execute(
            'DELETE FROM artist_representation_date WHERE id IN '
            f'({",".join("?" * len(artist_representation_date_ids))})',
            tuple(artist_representation_date_ids))
        cursor.execute(
            'DELETE FROM representation_date WHERE id IN '
            f'({",".join("?" * len(representation_date_ids))})',
            tuple(representation_date_ids))
        cursor.execute(
            'DELETE FROM representation WHERE id IN '
            f'({",".join("?" * len(representation_ids))})',
            tuple(representation_ids))

        for key, name in request.form.items():
            if not key.endswith('-name'):
                continue
            key = key.split('-', 1)[0]
            dates = request.form.getlist(f'{key}-dates')
            artists = set(request.form.getlist(f'{key}-artists'))
            cursor.execute('''
              INSERT INTO representation (spectacle_id, name)
              VALUES (?, ?)
              RETURNING id
            ''', (spectacle_id, name))
            representation_id = cursor.fetchone()['id']
            for representation_date in dates:
                if not representation_date:
                    continue
                cursor.execute('''
                  INSERT INTO representation_date (representation_id, date)
                  VALUES (?, ?)
                  RETURNING id
                ''', (representation_id, representation_date))
                representation_date_id = cursor.fetchone()['id']
                for artist_id in artists:
                    if not artist_id:
                        continue
                    cursor.execute('''
                      INSERT INTO
                        artist_representation_date
                        (representation_date_id, artist_id)
                      VALUES
                        (?, ?)
                    ''', (representation_date_id, artist_id))

        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('spectacle', spectacle_id=spectacle_id))

    cursor.execute('''
      SELECT
        spectacle.*,
        representation_id AS representation_id,
        representation.name AS representation_name,
        GROUP_CONCAT(DISTINCT sound_spectacle.sound_id) AS sound_ids,
        GROUP_CONCAT(DISTINCT makeup_spectacle.makeup_id) AS makeup_ids,
        GROUP_CONCAT(DISTINCT costume_spectacle.costume_id) AS costume_ids,
        GROUP_CONCAT(DISTINCT vehicle_spectacle.vehicle_id) AS vehicle_ids,
        GROUP_CONCAT(DISTINCT representation_date.date)
          AS representation_dates,
        GROUP_CONCAT(DISTINCT artist_representation_date.artist_id)
          AS artist_ids
      FROM spectacle
      LEFT JOIN sound_spectacle
      ON spectacle.id = sound_spectacle.spectacle_id
      LEFT JOIN makeup_spectacle
      ON spectacle.id = makeup_spectacle.spectacle_id
      LEFT JOIN costume_spectacle
      ON spectacle.id = costume_spectacle.spectacle_id
      LEFT JOIN vehicle_spectacle
      ON spectacle.id = vehicle_spectacle.spectacle_id
      LEFT JOIN representation
      ON spectacle.id = representation.spectacle_id
      LEFT JOIN representation_date
      ON representation.id = representation_date.representation_id
      LEFT JOIN artist_representation_date
      ON
        representation_date.id =
        artist_representation_date.representation_date_id
      WHERE spectacle.id = ?
      GROUP BY representation.id
      ORDER BY representation_name
    ''', (spectacle_id,))
    representations = cursor.fetchall()

    data = {}
    for table in tables:
        cursor.execute(f'SELECT * FROM {table} WHERE NOT hidden ORDER BY name')
        data[f'{table}s'] = cursor.fetchall()
    cursor.execute('''
      SELECT artist.id, person.name
      FROM artist
      JOIN person
      ON artist.person_id = person.id
      WHERE NOT hidden
      ORDER BY name
    ''')
    all_artists = cursor.fetchall()
    cursor.execute('''
      SELECT DISTINCT manager
      FROM spectacle
      WHERE manager IS NOT NULL
      ORDER BY id DESC LIMIT 100
    ''')
    all_managers = tuple(row['manager'] for row in cursor.fetchall())
    cursor.execute('''
      SELECT DISTINCT name
      FROM representation
      ORDER BY id DESC LIMIT 100
    ''')
    all_representations = tuple(row['name'] for row in cursor.fetchall())
    return render_template(
        'spectacle_update.jinja2.html', representations=representations,
        all_artists=all_artists, all_managers=all_managers,
        all_representations=all_representations, **data)


# Roadmaps
@app.route('/roadmap/<int:spectacle_id>')
@authenticated
def roadmap(spectacle_id):
    spectacle_data = get_spectacle_data(spectacle_id)
    html = render_template('roadmap.jinja2.html', **spectacle_data)
    place = spectacle_data['representations'][0]['place'].lower()
    return render_pdf(
        HTML(string=html), download_filename=f'{secure_filename(place)}.pdf')


@app.route('/roadmap/<int:spectacle_id>/send', methods=('GET', 'POST'))
@authenticated
def roadmap_send(spectacle_id):
    spectacle_data = get_spectacle_data(spectacle_id)

    if request.method == 'POST':
        to = tuple(
            mail for mail in request.form.getlist('mail')
            if mail and '@' in mail)
        place = spectacle_data['representations'][0]['place']
        subject = f'Feuille de route pour {place}'
        content = (
            'Bonjour,\n\n'
            'Veuillez trouver en pièce jointe la feuille de route '
            f'pour {place}.\n\n'
            'Cordialement,\n'
            'Mademoiselle Paillette'
        )
        html = render_template('roadmap.jinja2.html', **spectacle_data)
        pdf = HTML(string=html).write_pdf()
        attachments = {f'{place.lower()}.pdf': pdf}
        send_mail(to, subject, content, attachments)
        flash('La feuille de route a été envoyée.')
        return redirect(url_for('spectacle', spectacle_id=spectacle_id))

    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT name, mail
      FROM person
      WHERE person.id = ?
      UNION
      SELECT DISTINCT person.name, person.mail
      FROM person
      JOIN artist
      ON person.id = artist.person_id
      JOIN artist_representation_date
      ON artist.id = artist_representation_date.artist_id
      JOIN representation_date
      ON
        artist_representation_date.representation_date_id =
        representation_date.id
      JOIN representation
      ON representation_date.representation_id = representation.id
      WHERE representation.spectacle_id = ?
    ''', (session['person_id'], spectacle_id))
    recipients = cursor.fetchall()
    cursor.execute('SELECT name, mail FROM person ORDER BY name')
    persons = cursor.fetchall()
    return render_template(
        'roadmap_send.jinja2.html', recipients=recipients, persons=persons,
        **spectacle_data)


@app.route('/roadmap/<int:spectacle_id>/comment', methods=('POST',))
@authenticated
def roadmap_comment(spectacle_id):
    parameters = dict(request.form)
    parameters['spectacle_id'] = spectacle_id
    cursor = get_connection().cursor()
    cursor.execute('''
      UPDATE spectacle
      SET
        message = :message,
        payment = :payment,
        contact = :contact,
        planning = :planning,
        hosting = :hosting,
        meal = :meal,
        images_comment = :images_comment,
        sound_comment = :sound_comment,
        light_comment = :light_comment
      WHERE id = :spectacle_id
    ''', parameters)
    cursor.connection.commit()
    flash('Les données complémentaries ont été mises à jour.')
    return redirect(url_for('roadmap_send', spectacle_id=spectacle_id))


@app.route('/roadmap/<int:spectacle_id>/attach', methods=('POST',))
@authenticated
def roadmap_attach_image(spectacle_id):
    images = request.files.getlist('images')
    if images:
        cursor = get_connection().cursor()
        for image in images:
            filename = secure_filename(image.filename)
            if not filename:
                continue
            folder = Path(app.static_folder) / 'roadmap_images'
            folder.mkdir(exist_ok=True)
            image.save(folder / filename)
            with Image.open(folder / filename) as image:
                image.thumbnail((1000, 1000))
                image.save(folder / filename, optimize=True)
            cursor.execute('''
              INSERT INTO spectacle_image (spectacle_id, filename)
              VALUES (?, ?)
            ''', (spectacle_id, filename))
        cursor.connection.commit()
        flash('Les images ont été ajoutées.')
    return redirect(url_for('roadmap_send', spectacle_id=spectacle_id))


@app.route('/roadmap/image/<image_id>/detach', methods=('POST',))
@authenticated
def roadmap_detach_image(image_id):
    cursor = get_connection().cursor()
    cursor.execute('''
      DELETE FROM spectacle_image
      WHERE id = ?
      RETURNING spectacle_id, filename
    ''', (image_id,))
    image = cursor.fetchone() or abort(404)
    path = Path(app.static_folder) / 'roadmap_images' / image['filename']
    path.unlink(missing_ok=True)
    cursor.connection.commit()
    flash('L’image a été supprimée.')
    spectacle_id = image['spectacle_id']
    return redirect(url_for('roadmap_send', spectacle_id=spectacle_id))


# Follow-ups
@app.route('/artists/followup')
@app.route('/artists/followup/<int:year>/<int:month>')
@authenticated
def artists_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT artist.id, date, available
      FROM artist
      JOIN artist_availability
      ON artist.id = artist_availability.artist_id
      WHERE date BETWEEN ? AND ?
    ''', (start, stop))
    availabilities = cursor.fetchall()
    query = '''
      SELECT
        artist.id AS artist_id,
        artist.color,
        person.name || '-' || artist.id AS grouper,
        person.name,
        spectacle.trigram,
        representation_date.date
      FROM artist
      JOIN person
      ON artist.person_id = person.id
      LEFT JOIN (
        SELECT artist_id, representation_id, date
        FROM representation_date
        JOIN artist_representation_date
        ON
          artist_representation_date.representation_date_id =
          representation_date.id
        WHERE date BETWEEN ? AND ?
      ) AS representation_date
      ON artist.id = representation_date.artist_id
      LEFT JOIN representation
      ON representation_date.representation_id = representation.id
      LEFT JOIN spectacle
      ON representation.spectacle_id = spectacle.id
      WHERE (spectacle.trigram IS NOT NULL OR NOT artist.hidden)
    '''
    parameters = [start, stop]
    filter = session.get('artists-followup-filter')
    if filter:
        if filter[0] == 'availabilities':
            artists = {
                row['id'] for row in availabilities
                if row['available'] in filter[1]}
            query += f'AND artist.id IN ({",".join("?" * len(artists))})'
            parameters += artists
        elif filter[0] == 'spectacles':
            spectacles = filter[1] or (0,)
            query += f'AND spectacle.id IN ({",".join("?" * len(spectacles))})'
            parameters += spectacles
    cursor.execute(query, parameters)
    artists_spectacles = cursor.fetchall()
    return render_template(
        'artists_followup.jinja2.html',
        artists_spectacles=artists_spectacles, availabilities=availabilities,
        start=start, stop=stop, previous=previous, next=next)


# Follow-ups
@app.route('/artists/followup/<int:year>/<int:month>/filter',
           methods=('GET', 'POST'))
@authenticated
def artists_followup_filter(year, month):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()

    if request.method == 'POST':
        filter_type = request.form['type']
        try:
            if filter_type == 'availability':
                session['artists-followup-filter'] = (
                    'availabilities',
                    [int(i) for i in request.form.getlist('availabilities')])
            elif filter_type == 'spectacle':
                session['artists-followup-filter'] = (
                    'spectacles',
                    [int(i) for i in request.form.getlist('spectacles')])
            else:
                session.pop('artists-followup-filter', None)
        except Exception:
            session.pop('artists-followup-filter', None)
        return redirect(url_for('artists_followup', year=year, month=month))

    cursor.execute('''
      SELECT DISTINCT
        spectacle.id,
        spectacle.place || ' — ' || spectacle.event AS name
      FROM spectacle
      JOIN representation
      ON spectacle.id = representation.spectacle_id
      JOIN representation_date
      ON representation.id = representation_date.representation_id
      WHERE date BETWEEN ? AND ?
    ''', (start, stop))
    spectacles = cursor.fetchall()
    return render_template(
        'artists_followup_filter.jinja2.html', spectacles=spectacles)


@app.route('/costumes/followup')
@app.route('/costumes/followup/<int:year>/<int:month>')
@authenticated
def costumes_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        costume.id AS costume_id,
        costume.name || '-' || costume.id AS grouper,
        costume.name,
        costume.color,
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
      WHERE spectacle.trigram IS NOT NULL OR NOT costume.hidden
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
        makeup.name || '-' || makeup.id AS grouper,
        makeup.name,
        makeup.color,
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
      WHERE spectacle.trigram IS NOT NULL OR NOT makeup.hidden
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
        sound.name || '-' || sound.id AS grouper,
        sound.name,
        sound.color,
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
      WHERE spectacle.trigram IS NOT NULL OR NOT sound.hidden
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
        vehicle.name || '-' || vehicle.id AS grouper,
        vehicle.name,
        vehicle.color,
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
      WHERE spectacle.trigram IS NOT NULL OR NOT vehicle.hidden
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    vehicles_spectacles = cursor.fetchall()
    return render_template(
        'vehicles_followup.jinja2.html',
        vehicles_spectacles=vehicles_spectacles, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/availabilities/<int:artist_id>/<date>/update',
           methods=('GET', 'POST'))
@authenticated
def availabilities_update(artist_id, date):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['artist_id'] = artist_id

        cursor.execute('''
          DELETE FROM artist_representation_date
          WHERE id IN (
            SELECT artist_representation_date.id
            FROM artist_representation_date
            JOIN representation_date
            ON
              artist_representation_date.representation_date_id =
              representation_date.id
            WHERE artist_id = :artist_id
            AND date BETWEEN :date_from AND :date_to
          )
        ''', parameters)
        add_availability = (
            parameters['availability'] == 'available' and
            'spectacle_id' in parameters)
        if add_availability:
            cursor.execute('''
              INSERT INTO
                artist_representation_date(artist_id, representation_date_id)
              SELECT :artist_id, representation_date.id
              FROM representation_date
              JOIN representation
              WHERE spectacle_id = :spectacle_id
              AND date BETWEEN :date_from AND :date_to
            ''', parameters)

        cursor.execute('''
          DELETE FROM artist_availability
          WHERE artist_id = :artist_id
          AND date BETWEEN :date_from AND :date_to
        ''', parameters)
        if parameters['availability'] in ('unavailable', 'available'):
            parameters['available'] = parameters['availability'] == 'available'
            cursor.execute('''
              WITH RECURSIVE dates(date) AS (
                SELECT date(:date_from)
                UNION
                SELECT date(date, '+1 day')
                FROM dates
                WHERE date < date(:date_to)
              )
              INSERT INTO artist_availability(artist_id, date, available)
              SELECT :artist_id, date, :available
              FROM dates
            ''', parameters)

        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        year, month = date[:7].split('-')
        return redirect(url_for('artists_followup', year=year, month=month))

    cursor.execute('''
      SELECT
        person.name,
        artist_availability.available,
        representation.spectacle_id
      FROM artist
      JOIN person
      ON artist.person_id = person.id
      LEFT JOIN (
        SELECT artist_id, available
        FROM artist_availability
        WHERE date = ?
      ) AS artist_availability
      ON artist.id = artist_availability.artist_id
      LEFT JOIN (
        SELECT artist_id, spectacle_id
        FROM artist_representation_date
        JOIN (
          SELECT id, representation_id
          FROM representation_date
          WHERE date = ?
        ) AS representation_date
        ON
          artist_representation_date.representation_date_id =
          representation_date.id
        JOIN representation
        ON representation_date.representation_id = representation.id
      ) AS representation
      ON artist.id = representation.artist_id
      WHERE artist.id = ?
    ''', (date, date, artist_id))
    artist = cursor.fetchone() or abort(404)
    cursor.execute('''
      SELECT *
      FROM spectacle
      WHERE ? BETWEEN date_from AND date_to
    ''', (date,))
    spectacles = cursor.fetchall()
    return render_template(
        'availabilities_update.jinja2.html',
        artist=artist, spectacles=spectacles, date=date)


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
          SELECT mail
          FROM person
          WHERE mail IS NOT NULL
          AND id != ?
          AND id NOT IN (SELECT person_id FROM artist)
        ''', (person_id,))
        mails = tuple(row['mail'] for row in cursor.fetchall())
        if parameters['mail'] in mails:
            flash('Cet email est déjà utilisé.')
        else:
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
            return redirect(url_for('persons'))

    return render_template('person_update.jinja2.html', person=person)


@app.route('/persons')
@authenticated
def persons():
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT person.*
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
          SELECT mail
          FROM person
          WHERE mail IS NOT NULL
          AND id NOT IN (SELECT person_id FROM artist)
        ''')
        mails = tuple(row['mail'] for row in cursor.fetchall())
        if parameters['mail'] in mails:
            flash('Cet email est déjà utilisé.')
        else:
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
          SET name = :name, color = :color
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('costumes'))

    cursor.execute('SELECT * FROM costume WHERE id = ?', (costume_id,))
    costume = cursor.fetchone() or abort(404)
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
          SET name = :name, color = :color
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('makeups'))

    cursor.execute('SELECT * FROM makeup WHERE id = ?', (makeup_id,))
    makeup = cursor.fetchone() or abort(404)
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
          SET name = :name, color = :color
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('sounds'))

    cursor.execute('SELECT * FROM sound WHERE id = ?', (sound_id,))
    sound = cursor.fetchone() or abort(404)
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
            rented_to = :rented_to,
            details = :details
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('vehicles'))

    cursor.execute('SELECT * FROM vehicle WHERE id = ?', (vehicle_id,))
    vehicle = cursor.fetchone() or abort(404)
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
              rented_to, details)
          VALUES
            (:name, :color, :type, :license_plate, :rented,
             :rental_company_name, :rental_company_hours,
             :rental_company_address, :rented_from, :rented_to, :details)
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
        person.name,
        person.phone
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
        person.name,
        person.phone
      FROM artist
      JOIN person
      ON artist.person_id = person.id
      WHERE artist.id = ?
    ''', (artist_id,))
    artist = cursor.fetchone() or abort(404)
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
