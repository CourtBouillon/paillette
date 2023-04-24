PRAGMA foreign_keys=ON;

CREATE TABLE person (
  id INTEGER PRIMARY KEY,
  mail TEXT UNIQUE NOT NULL,
  firstname TEXT NOT NULL,
  lastname TEXT NOT NULL,
  phone TEXT,
  password TEXT,
  reset_password TEXT
);

CREATE TABLE tour (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT
);

CREATE TABLE spectacle (
  id INTEGER PRIMARY KEY,
  tour_id INTEGER REFERENCES tour(id),
  event TEXT NOT NULL,
  place TEXT NOT NULL,
  trigram TEXT NOT NULL
);

CREATE TABLE roadmap (
  id INTEGER PRIMARY KEY,
  spectacle_id INTEGER UNIQUE REFERENCES spectacle(id)
);

CREATE TABLE artist (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id),
  color TEXT
);

CREATE TABLE availability (
  id INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artist(id),
  date DATE NOT NULL
);

CREATE TABLE representation (
  id INTEGER PRIMARY KEY,
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id),
  date DATE NOT NULL
);

CREATE TABLE artist_representation (
  id INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artist(id),
  representation_id INTEGER NOT NULL REFERENCES representation(id)
);

CREATE TABLE costume (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT
);

CREATE TABLE costume_spectacle (
  id INTEGER PRIMARY KEY,
  costume_id INTEGER NOT NULL REFERENCES costume(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE makeup (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT
);

CREATE TABLE makeup_spectacle (
  id INTEGER PRIMARY KEY,
  makeup_id INTEGER NOT NULL REFERENCES makeup(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE sound (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT
);

CREATE TABLE sound_spectacle (
  id INTEGER PRIMARY KEY,
  sound_id INTEGER NOT NULL REFERENCES sound(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);

CREATE TABLE vehicle (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT
);

CREATE TABLE vehicle_spectacle (
  id INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicle(id),
  spectacle_id INTEGER NOT NULL REFERENCES spectacle(id)
);
