from flask import Flask, redirect, render_template, url_for

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='paillette.db')
app.config.from_envvar('PAILLETTE_CONFIG', silent=True)


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


@app.route('/shows')
def shows():
    return render_template('shows.jinja2.html')


@app.route('/add_show')
def add_show():
    return render_template('add_show.jinja2.html')


@app.route('/show')
def show():
    return render_template('show.jinja2.html')


@app.route('/update_show')
def update_show():
    return render_template('update_show.jinja2.html')


@app.route('/roadmap')
def roadmap():
    return render_template('roadmap.jinja2.html')


@app.route('/followups')
def followups():
    return render_template('followups.jinja2.html')


@app.route('/update_availabilities')
def update_availabilities():
    return render_template('update_availabilities.jinja2.html')


@app.route('/filter_availabilities')
def filter_availabilities():
    return render_template('filter_availabilities.jinja2.html')


@app.route('/tours')
def tours():
    return render_template('tours.jinja2.html')


@app.route('/tour')
def tour():
    return render_template('tour.jinja2.html')


@app.route('/update_tour')
def update_tour():
    return render_template('update_tour.jinja2.html')


@app.route('/add_tour')
def add_tour():
    return render_template('add_tour.jinja2.html')


@app.route('/profile')
def profile():
    return render_template('profile.jinja2.html')


@app.route('/users')
def users():
    return render_template('users.jinja2.html')


@app.route('/add_user')
def add_user():
    return render_template('add_user.jinja2.html')


@app.route('/costumes')
def costumes():
    return render_template('costumes.jinja2.html')


@app.route('/costume')
def costume():
    return render_template('costume.jinja2.html')


@app.route('/add_costume')
def add_costume():
    return render_template('add_costume.jinja2.html')


@app.route('/makeups')
def makeups():
    return render_template('makeups.jinja2.html')


@app.route('/makeup')
def makeup():
    return render_template('makeup.jinja2.html')


@app.route('/add_makeup')
def add_makeup():
    return render_template('add_makeup.jinja2.html')


@app.route('/sounds')
def sounds():
    return render_template('sounds.jinja2.html')


@app.route('/sound')
def sound():
    return render_template('sound.jinja2.html')


@app.route('/add_sound')
def add_sound():
    return render_template('add_sound.jinja2.html')


@app.route('/artists')
def artists():
    return render_template('artists.jinja2.html')


@app.route('/artist')
def artist():
    return render_template('artist.jinja2.html')


@app.route('/artist')
def add_artist():
    return render_template('add_artist.jinja2.html')


@app.route('/vehicules')
def vehicules():
    return render_template('vehicules.jinja2.html')


@app.route('/vehicule')
def vehicule():
    return render_template('vehicule.jinja2.html')


@app.route('/add_vehicule')
def add_vehicule():
    return render_template('add_vehicule.jinja2.html')
