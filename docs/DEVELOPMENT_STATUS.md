# Suivi du développement

Dernière mise à jour : 2026-09-14

## Cible actuelle

Transformer l’ancienne interface orientée préparation locale en gestionnaire de
bibliothèque connecté en permanence à l’Allmiibo.

## Terminé avant cette refonte

- Protocole BLE Pixl.js : lecture/écriture, dossiers, suppression et renommage.
- Synchronisation sûre : identique ignoré, différent remplacé, nouveau ajouté.
- Validation des limites de chemins Allmiibo avant transfert.
- Build Windows PyInstaller et workflow GitHub Release.

## Refonte en cours

- [x] Définir le nouveau workflow utilisateur.
- [x] Ajouter une couche métier pour une connexion persistante.
- [x] Prévoir le stockage temporaire Windows et son nettoyage automatique.
- [x] Remplacer l’interface par l’écran connexion puis l’explorateur distant.
- [x] Ajouter les actions fichier/dossier et le glisser-déposer.
- [x] Ajouter l’import ZIP guidé avec lien vers le dossier Google Drive.
- [x] Conserver les noms du Drive sans alias ni raccourcissement automatique.
- [x] Ajouter les liens DFU/releases et l’exigence Pixl.js 2.16+ pour Kirby Air Riders.
- [x] Ajouter les états de connexion, erreurs et progression.
- [x] Ajouter la reconnexion automatique avec temporisation progressive.
- [x] Rendre la destination du glisser-déposer explicite et déterministe.
- [x] Afficher l’espace disponible après chaque actualisation.
- [x] Ajouter la sélection par cases et la suppression groupée d’éléments.
- [x] Corriger le clic réel de la case globale et isoler l’indentation dans Nom.
- [x] Étendre les cases de suppression aux fichiers `.bin`.
- [x] Faire du clic dans le vide un retour explicite à la racine Bibliothèque.
- [x] Refuser les dossiers frères de même nom et verrouiller l’extension `.bin`.
- [x] Remplacer le débordement natif par un bouton `Plus` inline responsive.
- [x] Détailler les bilans de suppression et d’import ZIP dans le journal.
- [x] Appliquer une icône amiibo à la fenêtre et au package Windows.
- [x] Présenter la connexion initiale comme l’analyse de l’arborescence existante.
- [x] Permettre la fermeture pendant la recherche BLE et annuler celle-ci proprement.
- [x] Protéger `fav`, `data` et leurs parents contre toute suppression.
- [x] Compléter les tests métier et les tests d’interface.
- [x] Reconstruire et vérifier l’exécutable Windows.
- [x] Mettre à jour README.md et DESIGN.md.

## État des validations

- 38 tests unitaires réussis, dont les conflits de dossiers, le verrouillage de
  `.bin`, le retour à la racine, le menu `Plus`, la case globale et les cases
  protégées Qt, ainsi que l’annulation immédiate d’une recherche BLE active.
- Aperçus Qt desktop 1080×720 et compact 760×560 contrôlés avec le nouveau
  bandeau Drive/firmware.
- Détecteur Impeccable : aucune anomalie mécanique signalée.
- Aperçu natif de la sélection multiple et des dossiers protégés contrôlé.
- Build PyInstaller réussi avec PySide6 6.8.3.
- Auto-test du binaire : code de sortie `0`.
- Binaire : 42 675 251 octets ; SHA-256
  `48E29BDD86C223F31C38D54ACD7B31EC7CCAFE662F505433EE13457DB6320DBB`.
- Test matériel final toujours requis pour confirmer la durée de vie de la
  connexion sur un vrai Allmiibo.

## Validation attendue

- Tests unitaires avec un client VFS simulé.
- Smoke-test PySide6 hors écran.
- Build `.exe` avec PySide6 6.8.3 et self-test du binaire.
- Test matériel final à faire avec un Allmiibo réel connecté.
