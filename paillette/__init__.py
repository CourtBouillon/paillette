import sqlite3

from flask import Flask, g, redirect, render_template, session, url_for

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
    return redirect(url_for('login'))


@app.route('/login')
def login():
    return render_template('login.jinja2.html')


@app.route('/logout')
def logout():
    return redirect(url_for('login'))


@app.route('/lost_password')
def lost_password():
    return render_template('lost_password.jinja2.html')


# Shows
@app.route('/shows')
def shows():
    return render_template('shows.jinja2.html')


@app.route('/show_add')
def show_add():
    return render_template('show_add.jinja2.html')


@app.route('/show')
def show():
    return render_template('show.jinja2.html')


@app.route('/update_show')
def update_show():
    return render_template('update_show.jinja2.html')


@app.route('/roadmap')
def roadmap():
    return render_template('roadmap.jinja2.html')


@app.route('/roadmap_receivers')
def roadmap_receivers():
    return render_template('roadmap_receivers.jinja2.html')


# Follow-ups
@app.route('/followups')
def followups():
    return render_template('followups.jinja2.html')


@app.route('/update_availabilities')
def update_availabilities():
    return render_template('update_availabilities.jinja2.html')


@app.route('/filter_availabilities')
def filter_availabilities():
    return render_template('filter_availabilities.jinja2.html')


# Tours
@app.route('/tours')
def tours():
    return render_template('tours.jinja2.html')


@app.route('/tour')
def tour():
    return render_template('tour.jinja2.html')


@app.route('/update_tour')
def update_tour():
    return render_template('update_tour.jinja2.html')


@app.route('/tour_add')
def tour_add():
    return render_template('tour_add.jinja2.html')


# Users
@app.route('/profile')
def profile():
    return render_template('profile.jinja2.html')


@app.route('/users')
def users():
    return render_template('users.jinja2.html')


@app.route('/user_add')
def user_add():
    return render_template('user_add.jinja2.html')


# Costumes
@app.route('/costumes')
def costumes():
    return render_template('costumes.jinja2.html')


@app.route('/costume')
def costume():
    return render_template('costume.jinja2.html')


@app.route('/costume_add')
def costume_add():
    return render_template('costume_add.jinja2.html')


# Make-ups
@app.route('/makeups')
def makeups():
    return render_template('makeups.jinja2.html')


@app.route('/makeup')
def makeup():
    return render_template('makeup.jinja2.html')


@app.route('/makeup_add')
def makeup_add():
    return render_template('makeup_add.jinja2.html')


# Sounds
@app.route('/sounds')
def sounds():
    return render_template('sounds.jinja2.html')


@app.route('/sound')
def sound():
    return render_template('sound.jinja2.html')


@app.route('/sound_add')
def sound_add():
    return render_template('sound_add.jinja2.html')


# Artists
@app.route('/artists')
def artists():
    return render_template('artists.jinja2.html')


@app.route('/artist')
def artist():
    return render_template('artist.jinja2.html')


@app.route('/artist_add')
def artist_add():
    return render_template('artist_add.jinja2.html')


# Vehicules
@app.route('/vehicules')
def vehicules():
    return render_template('vehicules.jinja2.html')


@app.route('/vehicule')
def vehicule():
    return render_template('vehicule.jinja2.html')


@app.route('/vehicule_add')
def vehicule_add():
    return render_template('vehicule_add.jinja2.html')
