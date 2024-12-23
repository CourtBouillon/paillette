import calendar
import sqlite3
from datetime import date, datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from functools import wraps
from itertools import groupby
from locale import LC_ALL, setlocale
from pathlib import Path
from smtplib import SMTP_SSL
from subprocess import PIPE, run
from uuid import uuid4

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session,
    url_for)
from flask_weasyprint import HTML, render_pdf
from markupsafe import Markup
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

PNG_MAGIC_NUMBER = b'\x89\x50\x4e\x47\x0d\x0a\x1a\x0a'


setlocale(LC_ALL, 'fr_FR.utf8')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=b'change_me_in_configuration_file',
    DB='paillette.db',
    SMTP_HOSTNAME=None,
    SMTP_LOGIN=None,
    SMTP_PASSWORD=None,
    SMTP_FROM='sender@example.com',
    GIT_VERSION=(
        Path(app.root_path).parent / '.git' / 'refs' / 'heads' / 'main'
    ).read_text().strip()[:7],
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
      SELECT card.*
      FROM card
      JOIN card_spectacle
      ON card.id = card_spectacle.card_id
      WHERE card_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    cards = cursor.fetchall()
    cursor.execute('''
      SELECT beeper.*
      FROM beeper
      JOIN beeper_spectacle
      ON beeper.id = beeper_spectacle.beeper_id
      WHERE beeper_spectacle.spectacle_id = ?
    ''', (spectacle_id,))
    beepers = cursor.fetchall()
    cursor.execute('''
      SELECT id, filename
      FROM spectacle_image
      WHERE spectacle_id = ?
    ''', (spectacle_id,))
    images = cursor.fetchall()
    return {
        'representations': representations,
        'makeups': makeups,
        'sounds': sounds,
        'vehicles': vehicles,
        'costumes': costumes,
        'cards': cards,
        'beepers': beepers,
        'images': images,
    }


def send_mail(to, subject, content, pdfs=None):
    message = MIMEMultipart()
    message['From'] = app.config['SMTP_FROM']
    message['To'] = ', '.join(to)
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
def date_range(dates, format='%d/%m'):
    date_from, date_to = dates
    if not all(dates):
        return 'dates indéterminées'
    if isinstance(date_from, str):
        date_from = datetime.fromisoformat(date_from)
    if isinstance(date_to, str):
        date_to = datetime.fromisoformat(date_to)
    if date_from == date_to:
        return f'le {date_simple(date_from, format)}'
    else:
        return (
            f'du {date_simple(date_from, format)} '
            f'au {date_simple(date_to, format)}')


@app.template_filter('date_simple')
def date_simple(date_or_string, format='%d/%m'):
    if not date_or_string:
        return 'date indéterminée'
    if isinstance(date_or_string, str):
        date_or_string = date.fromisoformat(date_or_string)
    return date_or_string.strftime(format)


@app.template_filter('month_weeks')
def month_weeks(days):
    start, stop = days
    days = (start.replace(day=i) for i in range(start.day, stop.day + 1))
    grouped_days = {
       week: list(days) for week, days in
       groupby(days, lambda day: date.isocalendar(day).week)}
    return {week: (days[0], days[-1]) for week, days in grouped_days.items()}


@app.template_filter('isoweek')
def isoweek(day):
    return date.isocalendar(day).week


@app.template_filter('version')
def version(url):
    return f'{url}?{app.config["GIT_VERSION"]}'


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
    if type not in ('vehicle', 'makeup', 'sound', 'artist', 'costume', 'card', 'beeper'):
        return abort(404)

    cursor = get_connection().cursor()
    if request.method == 'POST':
        cursor.execute(f'UPDATE {type} SET hidden = TRUE WHERE id = ?', (id,))
        cursor.connection.commit()
        flash('L’élément a été supprimé.')
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
        GROUP_CONCAT(DISTINCT contract.artist_id) AS contract_artist_ids,
        GROUP_CONCAT(DISTINCT replace(vehicle.name, ',', ' ')) AS vehicles,
        GROUP_CONCAT(DISTINCT replace(makeup.name, ',', ' ')) AS makeups,
        GROUP_CONCAT(DISTINCT replace(sound.name, ',', ' ')) AS sounds,
        GROUP_CONCAT(DISTINCT replace(beeper.name, ',', ' ')) AS beepers,
        GROUP_CONCAT(DISTINCT replace(card.name, ',', ' ')) AS cards,
        GROUP_CONCAT(DISTINCT replace(person.name, ',', ' ')) AS artists,
        GROUP_CONCAT(
          DISTINCT replace(representation.name, ',', ' ')) AS representations
      FROM spectacle
      LEFT JOIN contract
      ON spectacle.id = contract.spectacle_id
      LEFT JOIN representation
      ON spectacle.id = representation.spectacle_id
      LEFT JOIN representation_date
      ON representation.id = representation_date.representation_id
      LEFT JOIN artist_representation_date
      ON representation_date.id = artist_representation_date.representation_date_id
      LEFT JOIN artist
      ON artist.id = artist_representation_date.artist_id
      LEFT JOIN person
      ON person.id = artist.person_id
      LEFT JOIN vehicle_spectacle
      ON spectacle.id = vehicle_spectacle.spectacle_id
      LEFT JOIN vehicle
      ON vehicle_spectacle.vehicle_id = vehicle.id
      LEFT JOIN makeup_spectacle
      ON spectacle.id = makeup_spectacle.spectacle_id
      LEFT JOIN makeup
      ON makeup_spectacle.makeup_id = makeup.id
      LEFT JOIN sound_spectacle
      ON spectacle.id = sound_spectacle.spectacle_id
      LEFT JOIN sound
      ON sound_spectacle.sound_id = sound.id
      LEFT JOIN beeper_spectacle
      ON spectacle.id = beeper_spectacle.spectacle_id
      LEFT JOIN beeper
      ON beeper_spectacle.beeper_id = beeper.id
      LEFT JOIN card_spectacle
      ON spectacle.id = card_spectacle.spectacle_id
      LEFT JOIN card
      ON card_spectacle.card_id = card.id
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
      GROUP BY spectacle.id
      ORDER BY date_from, date_to, place
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    spectacles = cursor.fetchall()
    return render_template(
        'spectacles.jinja2.html', spectacles=spectacles, start=start,
        stop=stop, previous=previous, next=next)


@app.route('/spectacles/filter', methods=('GET', 'POST'))
@authenticated
def spectacles_filter():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        filter_type = request.form.get('type')
        sql_request = '''
          SELECT
            spectacle.*,
            MIN(date) AS first_date,
            MAX(date) AS last_date,
            GROUP_CONCAT(DISTINCT contract.artist_id) AS contract_artist_ids,
            GROUP_CONCAT(DISTINCT replace(vehicle.name, ',', ' ')) AS vehicles,
            GROUP_CONCAT(DISTINCT replace(makeup.name, ',', ' ')) AS makeups,
            GROUP_CONCAT(DISTINCT replace(beeper.name, ',', ' ')) AS beepers,
            GROUP_CONCAT(DISTINCT replace(card.name, ',', ' ')) AS cards,
            GROUP_CONCAT(DISTINCT replace(person.name, ',', ' ')) AS artists,
            GROUP_CONCAT(
              DISTINCT replace(representation.name, ',', ' ')) AS representations
          FROM spectacle
          LEFT JOIN contract
          ON spectacle.id = contract.spectacle_id
          LEFT JOIN representation
          ON spectacle.id = representation.spectacle_id
          LEFT JOIN representation_date
          ON representation.id = representation_date.representation_id
          LEFT JOIN artist_representation_date
          ON representation_date.id = artist_representation_date.representation_date_id
          LEFT JOIN artist
          ON artist.id = artist_representation_date.artist_id
          LEFT JOIN person
          ON person.id = artist.person_id
          LEFT JOIN vehicle_spectacle
          ON spectacle.id = vehicle_spectacle.spectacle_id
          LEFT JOIN vehicle
          ON vehicle_spectacle.vehicle_id = vehicle.id
          LEFT JOIN makeup_spectacle
          ON spectacle.id = makeup_spectacle.spectacle_id
          LEFT JOIN makeup
          ON makeup_spectacle.makeup_id = makeup.id
          LEFT JOIN beeper_spectacle
          ON spectacle.id = beeper_spectacle.spectacle_id
          LEFT JOIN beeper
          ON beeper_spectacle.beeper_id = beeper.id
          LEFT JOIN card_spectacle
          ON spectacle.id = card_spectacle.spectacle_id
          LEFT JOIN card
          ON card_spectacle.card_id = card.id
        '''
        if filter_type == 'city':
            sql_request += '''
              WHERE place LIKE :city
            '''
        elif filter_type == 'date':
            if request.form['spectacle_to']:
                sql_request += '''
                  WHERE date BETWEEN :spectacle_from AND :spectacle_to
                '''
            else:
                sql_request += '''
                  WHERE date = :spectacle_from
                '''
        sql_request += '''
          GROUP BY spectacle.id
          ORDER BY date_from DESC, date_to DESC, place
        '''
        if filter_type in ('city', 'date'):
            cursor.execute(sql_request, request.form)
            spectacles = cursor.fetchall()
        else:
            spectacles = []
        return render_template(
            'spectacles_filter.jinja2.html', spectacles=spectacles,
            **request.form)

    return render_template('spectacles_filter.jinja2.html')


@app.route('/spectacle/create', methods=('GET', 'POST'))
@app.route('/spectacle/create/from/<int:spectacle_id>')
@authenticated
def spectacle_create(spectacle_id=None):
    tables = ('sound', 'makeup', 'costume', 'vehicle', 'card', 'beeper')
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['trigram'] = parameters['place'][:3].upper()
        parameters['pocket'] = 'pocket' in parameters
        cursor.execute('''
          INSERT INTO
            spectacle (
              event, place, travel_time, trigram, date_from, date_to, link,
              configuration, organizer, comment, pocket)
          VALUES
            (:event, :place, :travel_time, :trigram, :date_from, :date_to,
             :link, :configuration, :organizer, :comment, :pocket)
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

        contracts = set(request.form.getlist('artist-contracts'))
        for contract in contracts:
            cursor.execute('''
              INSERT INTO contract (spectacle_id, artist_id)
              VALUES (?, ?)
            ''', (spectacle_id, contract))

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
        year, month, _ = parameters['date_from'].split('-')
        return redirect(url_for('spectacles', year=year, month=month))

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
      SELECT DISTINCT name
      FROM representation
      ORDER BY id DESC LIMIT 100
    ''')
    all_representations = tuple(row['name'] for row in cursor.fetchall())
    from_data = {}
    if spectacle_id is not None:
        cursor.execute('''
          SELECT *
          FROM spectacle
          WHERE id = ?
        ''', (spectacle_id,))
        from_data = cursor.fetchone()
    return render_template(
        'spectacle_create.jinja2.html', all_artists=all_artists,
        all_representations=all_representations, from_data=from_data, **data)


@app.route('/spectacle/<int:spectacle_id>/update', methods=('GET', 'POST'))
@authenticated
def spectacle_update(spectacle_id):
    tables = ('sound', 'makeup', 'costume', 'vehicle', 'card', 'beeper')
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = spectacle_id
        parameters['pocket'] = 'pocket' in parameters
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
            comment = :comment,
            pocket = :pocket
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

        cursor.execute(
            'DELETE FROM contract WHERE spectacle_id = ?', (spectacle_id,))
        contracts = set(request.form.getlist('artist-contracts'))
        for contract in contracts:
            cursor.execute('''
              INSERT INTO contract (spectacle_id, artist_id)
              VALUES (?, ?)
            ''', (spectacle_id, contract))

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
        year, month, _ = parameters['date_from'].split('-')
        return redirect(url_for('spectacles', year=year, month=month))

    cursor.execute('''
      SELECT
        spectacle.*,
        representation.id AS representation_id,
        representation.name AS representation_name,
        GROUP_CONCAT(DISTINCT contract.artist_id) AS contract_artist_ids,
        GROUP_CONCAT(DISTINCT sound_spectacle.sound_id) AS sound_ids,
        GROUP_CONCAT(DISTINCT makeup_spectacle.makeup_id) AS makeup_ids,
        GROUP_CONCAT(DISTINCT costume_spectacle.costume_id) AS costume_ids,
        GROUP_CONCAT(DISTINCT vehicle_spectacle.vehicle_id) AS vehicle_ids,
        GROUP_CONCAT(DISTINCT beeper_spectacle.beeper_id) AS beeper_ids,
        GROUP_CONCAT(DISTINCT card_spectacle.card_id) AS card_ids,
        GROUP_CONCAT(DISTINCT representation_date.date)
          AS representation_dates,
        GROUP_CONCAT(DISTINCT artist_representation_date.artist_id)
          AS artist_ids
      FROM spectacle
      LEFT JOIN contract
      ON spectacle.id = contract.spectacle_id
      LEFT JOIN sound_spectacle
      ON spectacle.id = sound_spectacle.spectacle_id
      LEFT JOIN makeup_spectacle
      ON spectacle.id = makeup_spectacle.spectacle_id
      LEFT JOIN costume_spectacle
      ON spectacle.id = costume_spectacle.spectacle_id
      LEFT JOIN vehicle_spectacle
      ON spectacle.id = vehicle_spectacle.spectacle_id
      LEFT JOIN beeper_spectacle
      ON spectacle.id = beeper_spectacle.spectacle_id
      LEFT JOIN card_spectacle
      ON spectacle.id = card_spectacle.spectacle_id
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
      ORDER BY representation.name
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
      SELECT DISTINCT name
      FROM representation
      ORDER BY id DESC LIMIT 100
    ''')
    all_representations = tuple(row['name'] for row in cursor.fetchall())
    return render_template(
        'spectacle_update.jinja2.html', representations=representations,
        all_artists=all_artists, all_representations=all_representations,
        **data)


@app.route('/spectacle/delete/<int:spectacle_id>', methods=('GET', 'POST'))
@authenticated
def spectacle_remove(spectacle_id):
    cursor = get_connection().cursor()
    if request.method == 'POST':
        cursor.execute('''
          DELETE FROM spectacle
          WHERE id = :spectacle_id
        ''', (spectacle_id,))
        for table in ('sound', 'makeup', 'costume', 'vehicle', 'card', 'beeper'):
            cursor.execute(f'''
              DELETE FROM {table}_spectacle
              WHERE spectacle_id = :spectacle_id
            ''', (spectacle_id,))
        cursor.execute('''
          SELECT representation_date.id
          FROM representation
          JOIN representation_date
          ON representation.id = representation_date.representation_id
          WHERE spectacle_id = :spectacle_id
        ''', (spectacle_id,))
        representation_date_ids = tuple(row['id'] for row in cursor.fetchall())
        cursor.execute(f'''
          DELETE FROM artist_representation_date
          WHERE representation_date_id
          IN ({",".join("?" * len(representation_date_ids))})
        ''', representation_date_ids)
        cursor.execute(f'''
          DELETE FROM representation_date
          WHERE id IN ({",".join("?" * len(representation_date_ids))})
        ''', representation_date_ids)
        cursor.execute('''
          DELETE FROM representation
          WHERE spectacle_id = :spectacle_id
        ''', (spectacle_id,))
        cursor.execute('''
          DELETE FROM contract
          WHERE spectacle_id = :spectacle_id
        ''', (spectacle_id,))
        cursor.connection.commit()
        flash('Le spectacle a été supprimé.')
        return redirect(url_for('index'))

    cursor.execute('''
      SELECT place, event, date_from, date_to
      FROM spectacle
      WHERE id = :spectacle_id
    ''', (spectacle_id,))
    spectacle = cursor.fetchone()
    return render_template('spectacle_remove.jinja2.html', spectacle=spectacle)


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
            'Bises pailletées,\n'
            'Diff Prod Admin Elodie VACHERESSE : 06 87 11 49 94\n'
            'Artistique: Isabelle CAHAGNE : 06 83 28 25 60\n'
            'http://mademoiselle-paillette.com'
        )
        html = render_template('roadmap.jinja2.html', **spectacle_data)
        pdf = HTML(string=html).write_pdf()
        attachments = {f'{place.lower()}.pdf': pdf}
        send_mail(to, subject, content, attachments)
        flash('La feuille de route a été envoyée.')
        return redirect(url_for('spectacle_update', spectacle_id=spectacle_id))

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
            if filename.lower().endswith('.pdf'):
                command = [
                    'gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=png16m',
                    '-r480.0', '-sOutputFile=-', '-']
                input = image.stream.read()
                pngs = run(command, input=input, stdout=PIPE).stdout
                sub_images = []
                for i, png in enumerate(pngs[8:].split(PNG_MAGIC_NUMBER)):
                    filename = f'{filename[:-4]}-page{i}.png'
                    (folder / filename).write_bytes(PNG_MAGIC_NUMBER + png)
                    sub_images.append(filename)
            else:
                image.save(folder / filename)
                sub_images = [filename]
            for filename in sub_images:
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

    filter = session.get('artists-followup-filter')

    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT artist.id, date, available, available AS filter_column
      FROM artist
      JOIN artist_availability
      ON artist.id = artist_availability.artist_id
      WHERE date BETWEEN ? AND ?
      UNION
      SELECT artist.id, date, 1 AS available, 1 as filter_column
      FROM artist
      LEFT JOIN artist_representation_date
      ON artist.id = artist_representation_date.artist_id
      LEFT JOIN representation_date
      ON
        artist_representation_date.representation_date_id =
        representation_date.id
      WHERE date BETWEEN ? AND ?
      ORDER BY artist.id, date
    ''', [start, stop] * 2)
    availabilities = cursor.fetchall()
    availabilities_by_artist_by_day = {
        artist: {
            day: list(availabilities)
            for day, availabilities
            in groupby(availabilities, lambda row: row['date'])
        }
        for artist, availabilities
        in groupby(availabilities, lambda row: row['id'])
    }
    query = '''
      SELECT
        artist.id AS artist_id,
        artist.color,
        lower(person.name) || '-' || artist.id AS grouper,
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
            filter_list = availabilities
        elif filter[0] == 'spectacles':
            cursor.execute('''
              SELECT artist.id AS id, date, spectacle.id AS filter_column
              FROM artist
              LEFT JOIN artist_representation_date
              ON artist.id = artist_representation_date.artist_id
              LEFT JOIN representation_date
              ON
                artist_representation_date.representation_date_id =
                representation_date.id
              LEFT JOIN representation
              ON representation_date.representation_id = representation.id
              LEFT JOIN spectacle
              ON representation.spectacle_id = spectacle.id
              WHERE date BETWEEN ? AND ?
            ''', [start, stop])
            filter_list = cursor.fetchall()
        filter_start = datetime.fromisoformat(filter[2]).date()
        filter_stop = datetime.fromisoformat(filter[3]).date()
        artists = list({
            row['id'] for row in filter_list
            if row['filter_column'] in filter[1]
            and filter_start <= row['date'] <= filter_stop}) or (0,)
        query += f'AND artist.id IN ({",".join("?" * len(artists))})'
        parameters += artists
    query += '''
      ORDER BY grouper, date
    '''
    cursor.execute(query, parameters)
    spectacles_by_grouper_by_day = {
        grouper: {
            day: list(spectacles)
            for day, spectacles
            in groupby(spectacles, lambda row: row['date'])
        }
        for grouper, spectacles
        in groupby(cursor.fetchall(), lambda row: row['grouper'])
    }
    cursor.execute('''
      SELECT representation_date.id, date, trigram
      FROM spectacle
      JOIN representation
      ON spectacle.id = representation.spectacle_id
      JOIN representation_date
      ON representation.id = representation_date.representation_id
      WHERE date BETWEEN ? AND ?
      ORDER BY date
    ''', (start, stop))
    representation_dates_by_day = {
        day: list(representations)
        for day, representations
        in groupby(cursor.fetchall(), lambda row: row['date'])
    }
    return render_template(
        'artists_followup.jinja2.html',
        spectacles_by_grouper_by_day=spectacles_by_grouper_by_day,
        availabilities_by_artist_by_day=availabilities_by_artist_by_day,
        representation_dates_by_day=representation_dates_by_day,
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
                    [int(i) for i in request.form.getlist('availabilities')],
                    request.form['available_from'],
                    request.form['available_to'])
            elif filter_type == 'spectacle':
                session['artists-followup-filter'] = (
                    'spectacles',
                    [int(i) for i in request.form.getlist('spectacles')],
                    request.form['spectacle_from'],
                    request.form['spectacle_to'])
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
        'artists_followup_filter.jinja2.html', spectacles=spectacles,
        start=start, stop=stop)


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
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'costumes_followup.jinja2.html',
        costumes_spectacles=costumes_spectacles,
        spectacle_dates=spectacle_dates, start=start, stop=stop,
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
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'makeups_followup.jinja2.html',
        makeups_spectacles=makeups_spectacles, spectacle_dates=spectacle_dates,
        start=start, stop=stop, previous=previous, next=next)


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
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'sounds_followup.jinja2.html',
        sounds_spectacles=sounds_spectacles, spectacle_dates=spectacle_dates,
        start=start, stop=stop, previous=previous, next=next)


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
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'vehicles_followup.jinja2.html',
        vehicles_spectacles=vehicles_spectacles,
        spectacle_dates=spectacle_dates, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/cards/followup')
@app.route('/cards/followup/<int:year>/<int:month>')
@authenticated
def cards_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        card.id AS card_id,
        card.name || '-' || card.id AS grouper,
        card.name,
        card.color,
        spectacle.trigram,
        spectacle.date_from,
        spectacle.date_to
      FROM card
      LEFT JOIN card_spectacle
      ON card.id = card_spectacle.card_id
      LEFT JOIN (
        SELECT *
        FROM spectacle
        WHERE (date_from IS NULL AND date_to IS NULL)
        OR date_from BETWEEN ? AND ?
        OR date_to BETWEEN ? AND ?
      ) AS spectacle
      ON card_spectacle.spectacle_id = spectacle.id
      WHERE spectacle.trigram IS NOT NULL OR NOT card.hidden
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    cards_spectacles = cursor.fetchall()
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'cards_followup.jinja2.html',
        cards_spectacles=cards_spectacles,
        spectacle_dates=spectacle_dates, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/beepers/followup')
@app.route('/beepers/followup/<int:year>/<int:month>')
@authenticated
def beepers_followup(year=None, month=None):
    year, month, start, stop, previous, next = get_date_data(year, month)
    cursor = get_connection().cursor()
    cursor.execute('''
      SELECT
        beeper.id AS beeper_id,
        beeper.name || '-' || beeper.id AS grouper,
        beeper.name,
        beeper.color,
        spectacle.trigram,
        spectacle.date_from,
        spectacle.date_to
      FROM beeper
      LEFT JOIN beeper_spectacle
      ON beeper.id = beeper_spectacle.beeper_id
      LEFT JOIN (
        SELECT *
        FROM spectacle
        WHERE (date_from IS NULL AND date_to IS NULL)
        OR date_from BETWEEN ? AND ?
        OR date_to BETWEEN ? AND ?
      ) AS spectacle
      ON beeper_spectacle.spectacle_id = spectacle.id
      WHERE spectacle.trigram IS NOT NULL OR NOT beeper.hidden
    ''', (start, stop) * 2)  # Assume that spectacles last less than 1 month
    beepers_spectacles = cursor.fetchall()
    cursor.execute('''
      SELECT id, date_from, date_to, trigram
      FROM spectacle
      WHERE date_from BETWEEN ? AND ?
      OR date_to BETWEEN ? AND ?
    ''', (start, stop) * 2)
    spectacle_dates = cursor.fetchall()
    return render_template(
        'beepers_followup.jinja2.html',
        beepers_spectacles=beepers_spectacles,
        spectacle_dates=spectacle_dates, start=start, stop=stop,
        previous=previous, next=next)


@app.route('/availabilities/<int:artist_id>/<date>/update',
           methods=('POST',))
@authenticated
def availabilities_update(artist_id, date):
    cursor = get_connection().cursor()

    parameters = dict(request.form)
    parameters['artist_id'] = artist_id
    parameters['date'] = date

    return_value = ''

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
        AND date = :date
      )
    ''', parameters)
    if parameters['representation_date_id']:
        cursor.execute('''
          INSERT INTO
            artist_representation_date(artist_id, representation_date_id)
          VALUES
            (:artist_id, :representation_date_id)
        ''', parameters)
        cursor.execute('''
          SELECT trigram
          FROM spectacle
          JOIN representation
          ON spectacle.id = representation.spectacle_id
          JOIN representation_date
          ON representation.id = representation_date.representation_id
          WHERE representation_date.id = ?
        ''', (parameters['representation_date_id'],))
        return_value = cursor.fetchone()['trigram']

    cursor.execute('''
      DELETE FROM artist_availability
      WHERE artist_id = :artist_id
      AND date = :date
    ''', parameters)
    if parameters['available']:
        return_value = return_value or str(int(parameters['available']))
        cursor.execute('''
          INSERT INTO artist_availability(artist_id, date, available)
          VALUES (:artist_id, :date, :available)
        ''', parameters)

    cursor.connection.commit()
    return {'value': return_value}


@app.route('/followup/<type>/<int:id>/<date>/update', methods=('POST',))
@authenticated
def followup_update(type, id, date):
    if type not in ('vehicle', 'makeup', 'sound', 'costume', 'card', 'beeper'):
        return abort(404)

    cursor = get_connection().cursor()

    parameters = dict(request.form)
    parameters['id'] = id
    parameters['date'] = date
    date = datetime.fromisoformat(date).date()

    if parameters['spectacle_id']:
        cursor.execute(f'''
          INSERT INTO {type}_spectacle ({type}_id, spectacle_id)
          VALUES (:id, :spectacle_id)
        ''', parameters)
        cursor.execute('''
          SELECT trigram, date_from, date_to
          FROM spectacle
          WHERE id = :spectacle_id
        ''', parameters)
        spectacle = cursor.fetchone()
        return_value = spectacle['trigram']
        previous = (date - spectacle['date_from']).days
        next = (spectacle['date_to'] - date).days
        removed = []
    else:
        cursor.execute(f'''
          DELETE FROM {type}_spectacle
          WHERE {type}_id = :id
          AND spectacle_id IN (
            SELECT id
            FROM spectacle
            WHERE :date BETWEEN date_from AND date_to
          )
          RETURNING spectacle_id
        ''', parameters)
        spectacle_ids = tuple(row['spectacle_id'] for row in cursor.fetchall())
        cursor.execute(
            'SELECT trigram, date_from, date_to FROM spectacle WHERE id IN '
            f'({",".join("?" * len(spectacle_ids))})',
            tuple(spectacle_ids))
        removed = tuple({
            'value': spectacle['trigram'],
            'previous': (date - spectacle['date_from']).days,
            'next': (spectacle['date_to'] - date).days,
        } for spectacle in cursor.fetchall())
        return_value, previous, next = '', 0, 0

    cursor.connection.commit()
    return {
        'value': return_value,
        'previous': previous,
        'next': next,
        'removed': removed,
    }


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
                phone = :phone,
                comment = :comment
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
              INSERT INTO person (firstname, lastname, mail, phone, comment)
              VALUES (:firstname, :lastname, :mail, :phone, :comment)
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
        return redirect(url_for('costumes', _anchor=f'costume-{costume_id}'))

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
        return redirect(url_for('makeups', _anchor=f'makeup-{makeup_id}'))

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
        return redirect(url_for('sounds', _anchor=f'sound-{sound_id}'))

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
        return redirect(url_for('vehicles', _anchor=f"vehicle-{ vehicle_id }"))

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
            phone = :phone,
            comment = :comment
          WHERE id = :person_id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('artists', _anchor=f'artist-{artist_id}'))

    cursor.execute('''
      SELECT
        artist.*,
        person.mail,
        person.firstname,
        person.lastname,
        person.name,
        person.phone,
        person.comment
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
          INSERT INTO person (mail, firstname, lastname, phone, comment)
          VALUES (:mail, :firstname, :lastname, :phone, :comment)
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


# Credit cards
@app.route('/cards')
@authenticated
def cards():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM card ORDER BY name')
    cards = cursor.fetchall()
    return render_template('cards.jinja2.html', cards=cards)


@app.route('/card/<int:card_id>/update', methods=('GET', 'POST'))
@authenticated
def card_update(card_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = card_id
        cursor.execute('''
          UPDATE card
          SET name = :name, color = :color
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('cards', _anchor=f'card-{card_id}'))

    cursor.execute('SELECT * FROM card WHERE id = ?', (card_id,))
    card = cursor.fetchone() or abort(404)
    return render_template('card_update.jinja2.html', card=card)


@app.route('/card/create', methods=('GET', 'POST'))
@authenticated
def card_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
          INSERT INTO card (name, color)
          VALUES (:name, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('La carte bleue a été créée.')
        return redirect(url_for('cards'))

    return render_template('card_create.jinja2.html')


# Make-ups
@app.route('/beepers')
@authenticated
def beepers():
    cursor = get_connection().cursor()
    cursor.execute('SELECT * FROM beeper ORDER BY name')
    beepers = cursor.fetchall()
    return render_template('beepers.jinja2.html', beepers=beepers)


@app.route('/beeper/<int:beeper_id>/update', methods=('GET', 'POST'))
@authenticated
def beeper_update(beeper_id):
    cursor = get_connection().cursor()

    if request.method == 'POST':
        parameters = dict(request.form)
        parameters['id'] = beeper_id
        cursor.execute('''
          UPDATE beeper
          SET name = :name, color = :color
          WHERE id = :id
        ''', parameters)
        cursor.connection.commit()
        flash('Les informations ont été sauvegardées.')
        return redirect(url_for('beepers', _anchor=f'beeper-{beeper_id}'))

    cursor.execute('SELECT * FROM beeper WHERE id = ?', (beeper_id,))
    beeper = cursor.fetchone() or abort(404)
    return render_template('beeper_update.jinja2.html', beeper=beeper)


@app.route('/beeper/create', methods=('GET', 'POST'))
@authenticated
def beeper_create():
    if request.method == 'POST':
        cursor = get_connection().cursor()
        parameters = dict(request.form)
        cursor.execute('''
          INSERT INTO beeper (name, color)
          VALUES (:name, :color)
        ''', parameters)
        cursor.connection.commit()
        flash('Le bit d’autoroute a été créée.')
        return redirect(url_for('beepers'))

    return render_template('beeper_create.jinja2.html')
