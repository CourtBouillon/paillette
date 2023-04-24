import sqlite3
from email.message import EmailMessage
from functools import wraps
from smtplib import SMTP_SSL
from uuid import uuid4

from flask import (
    Flask, Markup, abort, flash, g, redirect, render_template, request,
    session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='paillette.db')
app.config.from_envvar('PAILLETTE_CONFIG', silent=True)


def get_connection():
    if not hasattr(g, 'connection'):
        g.connection = sqlite3.connect(app.config['DB'])
        g.connection.row_factory = sqlite3.Row
        cursor = g.connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
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
            'SELECT id, password FROM person WHERE mail = ?',
            (request.form['login'],))
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
        connection = get_connection()
        cursor = connection.cursor()
        uuid = str(uuid4())
        mail = request.form['mail']
        cursor.execute('''
            UPDATE person
            SET reset_password = ?
            WHERE mail = ?
            RETURNING id, firstname, lastname
        ''', (uuid, mail))
        person = cursor.fetchone()
        connection.commit()
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
    connection = get_connection()
    cursor = connection.cursor()
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
        connection.commit()
        flash('Le mot de passe a été modifié, merci de vous connecter.')
        return redirect(url_for('login'))
    return render_template('password_reset.jinja2.html')


# Spectacles
@app.route('/spectacles')
@authenticated
def spectacles():
    return render_template('spectacles.jinja2.html')


@app.route('/spectacle/create')
def spectacle_create():
    return render_template('spectacle_create.jinja2.html')


@app.route('/spectacle')
def spectacle():
    return render_template('spectacle.jinja2.html')


@app.route('/spectacle/update')
def spectacle_update():
    return render_template('spectacle_update.jinja2.html')


# Roadmaps
@app.route('/roadmap')
def roadmap():
    return render_template('roadmap.jinja2.html')


@app.route('/roadmap/send')
def roadmap_send():
    return render_template('roadmap_send.jinja2.html')


# Follow-ups
@app.route('/followups')
def followups():
    return render_template('followups.jinja2.html')


@app.route('/availabilities/update')
def availabilities_update():
    return render_template('availabilities_update.jinja2.html')


# Tours
@app.route('/tours')
def tours():
    return render_template('tours.jinja2.html')


@app.route('/tour')
def tour():
    return render_template('tour.jinja2.html')


@app.route('/tour/update')
def tour_update():
    return render_template('tour_update.jinja2.html')


@app.route('/tour/create')
def tour_create():
    return render_template('tour_create.jinja2.html')


# Persons
@app.route('/person', methods=('GET', 'POST'))
@app.route('/person/<int:person_id>', methods=('GET', 'POST'))
@authenticated
def person(person_id=None):
    person = g.person if person_id is None else get_person_from_id(person_id)

    if request.method == 'POST':
        password_match = (
            request.form.get('password') ==
            request.form.get('confirm_password'))
        if not password_match:
            flash('Les deux mots de passe doivent être les mêmes.')
            return redirect(url_for('person', person_id=person_id))

        connection = get_connection()
        cursor = connection.cursor()
        parameters = dict(request.form)
        parameters['id'] = person['id']
        cursor.execute('''
            UPDATE person
            SET mail = :mail, firstname = :firstname, lastname = :lastname,
                phone = :phone
            WHERE id = :id
        ''', parameters)
        if (password := request.form.get('password')):
            cursor.execute(
                'UPDATE person SET password = ? WHERE id = ?',
                (generate_password_hash(password), person['id']))
        connection.commit()
        flash('Les informations ont été sauvegardées')
        return redirect(url_for('person', person_id=person_id))

    return render_template('person.jinja2.html', person=person)


@app.route('/persons')
def persons():
    return render_template('persons.jinja2.html')


@app.route('/person/create')
def person_create():
    return render_template('person_create.jinja2.html')


# Costumes
@app.route('/costumes')
def costumes():
    return render_template('costumes.jinja2.html')


@app.route('/costume')
def costume():
    return render_template('costume.jinja2.html')


@app.route('/costume/create')
def costume_create():
    return render_template('costume_create.jinja2.html')


# Make-ups
@app.route('/makeups')
def makeups():
    return render_template('makeups.jinja2.html')


@app.route('/makeup')
def makeup():
    return render_template('makeup.jinja2.html')


@app.route('/makeup/create')
def makeup_create():
    return render_template('makeup_create.jinja2.html')


# Sounds
@app.route('/sounds')
def sounds():
    return render_template('sounds.jinja2.html')


@app.route('/sound')
def sound():
    return render_template('sound.jinja2.html')


@app.route('/sound/create')
def sound_create():
    return render_template('sound_create.jinja2.html')


# Artists
@app.route('/artists')
def artists():
    return render_template('artists.jinja2.html')


@app.route('/artist')
def artist():
    return render_template('artist.jinja2.html')


@app.route('/artist/create')
def artist_create():
    return render_template('artist_create.jinja2.html')


# Vehicles
@app.route('/vehicles')
def vehicles():
    return render_template('vehicles.jinja2.html')


@app.route('/vehicle')
def vehicle():
    return render_template('vehicle.jinja2.html')


@app.route('/vehicle/create')
def vehicle_create():
    return render_template('vehicle_create.jinja2.html')
