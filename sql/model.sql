PRAGMA foreign_keys=ON;

CREATE TABLE person (
  id INTEGER PRIMARY KEY,
  mail TEXT,
  firstname TEXT NOT NULL,
  lastname TEXT NOT NULL,
  name TEXT AS (firstname || ' ' || lastname),
  phone TEXT NOT NULL,
  password TEXT,
  reset_password TEXT,
  comment TEXT
);

CREATE TABLE spectacle (
  id INTEGER PRIMARY KEY,
  event TEXT NOT NULL,
  event_link TEXT,
  place TEXT NOT NULL,
  configuration TEXT NOT NULL,
  travel_time TEXT,
  link TEXT,
  organizer TEXT,
  trigram TEXT NOT NULL,
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  message TEXT,
  payment TEXT,
  contact TEXT,
  planning TEXT,
  hosting TEXT,
  meal TEXT,
  images_comment TEXT,
  sound_comment TEXT,
  light_comment TEXT,
  comment TEXT,
  pocket BOOLEAN
);

CREATE TABLE spectacle_image (
  id INTEGER PRIMARY KEY,
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id),
  filename TEXT
);

CREATE TABLE artist (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE contract (
  id INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artist(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE artist_availability (
  id INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artist(id),
  date DATE NOT NULL,
  available BOOLEAN NOT NULL
);

CREATE TABLE representation (
  id INTEGER PRIMARY KEY,
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id),
  name TEXT NOT NULL
);

CREATE TABLE representation_date (
  id INTEGER PRIMARY KEY,
  representation_id INTEGER NOT NULL REFERENCES representation(id),
  date DATE NOT NULL
);

CREATE TABLE artist_representation_date (
  id INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artist(id),
  representation_date_id INTEGER NOT NULL REFERENCES representation_date(id)
);

CREATE TABLE costume (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE costume_spectacle (
  id INTEGER PRIMARY KEY,
  costume_id INTEGER NOT NULL REFERENCES costume(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE makeup (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE makeup_spectacle (
  id INTEGER PRIMARY KEY,
  makeup_id INTEGER NOT NULL REFERENCES makeup(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE sound (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE sound_spectacle (
  id INTEGER PRIMARY KEY,
  sound_id INTEGER NOT NULL REFERENCES sound(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE vehicle (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  type TEXT,
  license_plate TEXT,
  rented BOOLEAN NOT NULL,
  rental_company_name TEXT,
  rental_company_hours TEXT,
  rental_company_address TEXT,
  rented_from DATE,
  rented_to DATE,
  details TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE vehicle_spectacle (
  id INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicle(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE card (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE card_spectacle (
  id INTEGER PRIMARY KEY,
  card_id INTEGER NOT NULL REFERENCES card(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE beeper (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  hidden BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE beeper_spectacle (
  id INTEGER PRIMARY KEY,
  beeper_id INTEGER NOT NULL REFERENCES beeper(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);
