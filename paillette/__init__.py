import sqlite3
from email.message import EmailMessage
from smtplib import SMTP_SSL
from uuid import uuid4

from flask import (
    Flask, flash, g, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash

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


def get_user():
    if 'person_id' not in session:
        return None
    if not hasattr(g, 'person'):
        cursor = get_connection().cursor()
        cursor.execute(
            'SELECT *, person.firstname || " " || person.lastname AS name '
            'FROM person WHERE id = (?)',
            (session['person_id'],))
        g.person = cursor.fetchone()
    return g.person


# Common
@app.route('/')
def index():
    if get_user():
        return redirect(url_for(''))
    return redirect(url_for('login'))


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
        flash('L’identifiant ou le mot de passe est incorrect')
        return redirect(url_for('login'))
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    session.pop('person_id', None)
    return redirect(url_for('login'))


@app.route('/lost_password', methods=('GET', 'POST'))
def lost_password():
    if request.method == 'POST':
        connection = get_connection()
        cursor = connection.cursor()
        uuid = str(uuid4())
        cursor.execute('''
            UPDATE person
            SET reset_password = ?
            WHERE mail = ?
            RETURNING id, firstname, lastname
        ''', (uuid, request.form['mail'],))
        person = cursor.fetchone()
        connection.commit()
        if person:
            smtp = SMTP_SSL(app.config['SMTP_HOSTNAME'])
            smtp.set_debuglevel(1)
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
                f'{url_for("reset_password", uuid=uuid, _external=True)}\n\n'
                'Si vous n’êtes pas à l’origine de cette demande, vous pouvez '
                'ignorer ce message.'
            )
            smtp.send_message(message)
            smtp.quit()
        flash('Un message vous a été envoyé si votre email est correct')
        return redirect(url_for('login'))
    return render_template('lost_password.jinja2.html')


# Spectacles
@app.route('/spectacles')
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
@app.route('/person')
def person():
    return render_template('profile.jinja2.html')


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
