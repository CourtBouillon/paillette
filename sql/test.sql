INSERT INTO person (mail, firstname, lastname, phone) VALUES
('elodie@example.com', 'Élodie', 'Dulac', '01 23 45 67 89'),
('isabelle@example.com', 'Isabelle', 'Leclerc', '01 23 45 67 10'),
('amandine@example.com', 'Amandine', 'Camala', '01 23 45 67 80'),
('lucile@example.com', 'Lucile', 'Gérin', '01 23 45 67 81'),
('fabrice@example.com', 'Fabrice', 'Duplan', '01 23 45 67 82'),
('samantha@example.com', 'Samantha', 'Labale', '01 23 45 67 83'),
('claire@example.com', 'Claire', 'Touillat', '01 23 45 67 84'),
('charly@example.com', 'Charly', 'Perdon', '01 23 45 67 85'),
('bertrand@example.com', 'Bertrand', 'Klamir', '01 23 45 67 86');

INSERT INTO spectacle (event, place, travel_time, trigram, date_from, date_to) VALUES
('Vive le printemps', 'Chamonix', '2h', 'CHA', '2023-01-23', '2023-01-25'),
('Fête de la ville', 'Besançon', '2h30', 'BES', '2023-02-01', '2023-02-07'),
('Défilé de la Tour Eiffel', 'Paris', '4h30', 'PAR', '2023-02-10', '2023-02-12'),
('Carnaval', 'Grenoble', '1h30', 'GRE', '2023-03-01', '2023-03-03');

INSERT INTO representation (name, spectacle_id) VALUES
('Les sorcières', 1),
('Échasses de rue', 2),
('La grande bulle', 2),
('Défilé', 3),
('Déambulations', 4);

INSERT INTO representation_date (representation_id, date) VALUES
(1, '2023-01-24'),
(2, '2023-02-02'),
(2, '2023-02-04'),
(3, '2023-02-03'),
(3, '2023-02-04'),
(3, '2023-02-05'),
(3, '2023-02-06'),
(4, '2023-02-11'),
(5, '2023-03-01'),
(5, '2023-03-02'),
(5, '2023-03-03');

INSERT INTO makeup (name, color) VALUES
('Poissons', '#0000ff'),
('Végétaux', '#008800'),
('Corail', '#888800'),
('Nuit', '#000088'),
('Petite boîte', NULL);

INSERT INTO makeup_spectacle (makeup_id, spectacle_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(2, 3),
(3, 3),
(1, 4),
(5, 4);

INSERT INTO costume (name, color) VALUES
('Clown', '#0000FF'),
('Bulle', '#008800'),
('Paillettes', NULL);

INSERT INTO costume_spectacle (costume_id, spectacle_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(2, 3),
(3, 3),
(1, 4);

INSERT INTO sound (name, color) VALUES
('Enceintes', '#0000FF'),
('Gros sound system', '#008800'),
('Kit de son', NULL);

INSERT INTO sound_spectacle (sound_id, spectacle_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(2, 3),
(3, 3),
(1, 4);

INSERT INTO vehicle (name, color, type, license_plate, rented, rental_company_name, rental_company_hours, rental_company_address, rented_from, rented_to) VALUES
('Gros camion', '#0000FF', 'Camion', 'XX-777-XX', TRUE, 'Loca-Voiture', 'Du lundi au vendredi de 6h à 22h
Du samedi au dimanche de 7h à 20h', '6 rue de la barre
69001 Lyon', '2023-02-02', '2023-04-01'),
('Voiture de Paillette', '#008800', 'Voiture', 'YY-888-YY', FALSE, NULL, NULL, NULL, NULL, NULL);

INSERT INTO vehicle_spectacle (vehicle_id, spectacle_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(2, 3),
(2, 4);

INSERT INTO artist (person_id, color) VALUES
(3, '#800080'),
(4, '#008800'),
(5, '#880000'),
(6, '#080080'),
(7, '#880000'),
(8, '#800080'),
(9, '#800008');

INSERT INTO artist_representation_date (representation_date_id, artist_id) VALUES
(1, 1),
(1, 2),
(2, 3),
(2, 4),
(3, 3),
(3, 4),
(4, 1),
(4, 5),
(4, 6),
(5, 1),
(5, 5),
(5, 6),
(6, 1),
(6, 5),
(7, 1),
(7, 5),
(8, 6),
(9, 2),
(9, 4),
(10, 2),
(10, 4),
(11, 2),
(11, 4);

INSERT INTO artist_availability (artist_id, date, available) VALUES
(1, '2023-03-27', false),
(1, '2023-03-28', true),
(1, '2023-03-29', true);
INSERT INTO artist_availability (artist_id, date, available)
SELECT artist_id, date, true
FROM artist_representation_date
JOIN representation_date
ON artist_representation_date.representation_date_id = representation_date.id;
