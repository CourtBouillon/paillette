INSERT INTO person (mail, firstname, lastname, phone) VALUES
('elodie@example.com', 'Élodie', 'Admin', '01 23 45 67 89'),
('amandine@example.com', 'Amandine', 'Échasses', '01 23 45 67 80');

INSERT INTO makeup (name, color) VALUES
('Poissons', '#0000ff'),
('Végétaux', '#008800'),
('Corail', '#888800'),
('Nuit', '#000088'),
('Inconnue', NULL);

INSERT INTO costume (name, color) VALUES
('Clown', '#0000FF'),
('Bulle', '#008800'),
('Paillettes', NULL);

INSERT INTO sound (name, color) VALUES
('Enceintes', '#0000FF'),
('Gros sound system', '#008800'),
('Kit de son', NULL);

INSERT INTO vehicle (name, color, type, license_plate, rented, rental_company_name, rental_company_hours, rental_company_address, rented_from, rented_to) VALUES
('Gros camion', '#0000FF', 'Camion', 'XX-777-XX', TRUE, 'Loca-Voiture', 'Du lundi au vendredi de 6h à 22h\nDu samedi au dimanche de 7h à 20h', '6 rue de la barre\n69001 Lyon', '2023-02-02', '2023-04-01'),
('Voiture de Paillette', '#008800', 'Voiture', 'YY-888-YY', FALSE, NULL, NULL, NULL, NULL, NULL);

INSERT INTO artist (person_id, color) VALUES
(2, '#880000');
