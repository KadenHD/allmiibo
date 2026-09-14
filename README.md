# Allmiibo Manager

Application Windows pour gérer directement la bibliothèque d’un
Allmiibo/Pixl.js par Bluetooth, sans manipuler ses disques ou ses dossiers
internes.

## Utilisation

1. Placez l’Allmiibo en mode **Bluetooth Transmission**.
2. Lancez `AllmiiboManager.exe` : la recherche et la connexion sont automatiques.
3. Gérez les amiibos depuis l’arborescence affichée par l’application.

La connexion BLE reste ouverte tant que l’application fonctionne. Si elle est
interrompue, l’écran de connexion explique quoi vérifier et relance
automatiquement la recherche avec une temporisation progressive. Le bouton
permet aussi une nouvelle tentative immédiate.

### Ajouter ses propres amiibos

Utilisez **Ajouter** pour sélectionner un ou plusieurs fichiers `.bin`, ou
**Ajouter un dossier** pour conserver une organisation existante. Les fichiers
et dossiers peuvent aussi être déposés directement sur l’arborescence.

Les noms des fichiers et dossiers sont conservés tels quels. L’application ne
fabrique ni alias ni nom raccourci. Si un ajout manuel dépasse une limite du
protocole de l’appareil, l’envoi est arrêté avec une erreur explicite au lieu de
modifier silencieusement le nom.

### Mettre à jour depuis la bibliothèque partagée

Ouvrez le [dossier Google Drive des amiibos](https://drive.google.com/drive/folders/1fNo0qv-6GnMwNWXwZ6WLZI5LQzH-jX9f),
téléchargez le dossier au format ZIP, puis utilisez **Importer le ZIP** dans
l’application. Les noms présents dans cette archive sont déjà définitifs et
sont conservés sans transformation.

Après téléchargement, cliquez sur **Importer le ZIP** ou déposez l’archive dans
l’application. La mise à jour applique les règles suivantes :

- même contenu : fichier ignoré ;
- contenu différent : fichier remplacé de manière sûre ;
- nouveau fichier : fichier ajouté ;
- fichier personnel absent du ZIP : fichier conservé.

L’archive est préparée dans le dossier temporaire de Windows, puis les données
temporaires sont automatiquement supprimées. Aucun dossier `data/` n’est demandé
à l’utilisateur.

### Firmware Pixl.js

**Kirby Air Riders nécessite le firmware Pixl.js 2.16 ou plus récent.** La
release 2.16.0 ajoute la prise en charge des amiibos V3 utilisés par le jeu.

- [Mettre à jour en DFU](https://thegecko.github.io/web-bluetooth-dfu)
- [Télécharger les releases du firmware Pixl.js](https://github.com/solosky/pixl.js/releases)

### Gérer l’arborescence

Depuis la barre d’actions ou le menu contextuel :

- créer un dossier ;
- renommer un fichier ou un dossier ; l’extension `.bin` reste verrouillée lors
  du renommage d’un amiibo ;
- cocher plusieurs fichiers et/ou dossiers dans la première colonne, ou utiliser
  sa case d’en-tête pour sélectionner tous les éléments supprimables, puis les
  supprimer ensemble après une confirmation unique ;
- supprimer ponctuellement le fichier ou dossier sélectionné ;
- actualiser l’état réel de la bibliothèque.

Deux dossiers portant le même nom, sans tenir compte des majuscules, ne peuvent
pas être créés dans un même répertoire. Le même nom reste autorisé dans deux
répertoires différents.

Les cases de `fav`, `data` et de leurs dossiers parents sont visibles mais
désactivées : ces dossiers ne peuvent être ni sélectionnés pour suppression, ni
supprimés. `fav` et `data` ne peuvent pas non plus être renommés.
L’indentation de l’arborescence reste limitée à la colonne **Nom** : toutes les
cases demeurent alignées et accessibles, même pour les sous-dossiers profonds.
Un clic dans la zone vide de l’arborescence réactive **Bibliothèque** comme
destination racine et annule l’ancienne sélection.

Quand la largeur manque, les actions qui ne tiennent plus sont regroupées dans
un bouton **Plus** placé juste après les dernières actions visibles. Le panneau
**Détails** conserve la liste des cibles et les totaux fichiers/dossiers pour une
suppression, ainsi que les bilans d’extraction et de synchronisation d’un ZIP.

La destination d’un glisser-déposer correspond au dossier survolé et reste
visible dans la zone d’activité pendant l’envoi. L’en-tête indique aussi l’espace
disponible après chaque actualisation.

Toutes les opérations sont limitées à la bibliothèque amiibo. Les données
système de l’appareil ne sont pas exposées par l’interface.

## Développement

Prérequis : Python 3.10 ou plus récent et Windows 10 ou plus récent pour le BLE.

```powershell
python -m pip install -r ./requirements-gui.txt
python ./allmiibo_gui.py
```

Tests :

```powershell
python -m unittest discover -v
```

Construction de l’exécutable :

```powershell
./build.ps1
```

Le résultat est créé dans `dist/AllmiiboManager.exe`. PySide6 6.8.3 est épinglé
car les versions plus récentes testées provoquaient un conflit de DLL Qt dans le
package PyInstaller Windows.

## Releases GitHub

Le workflow `.github/workflows/release.yml` lance les tests, construit le `.exe`,
exécute son smoke-test et génère un checksum SHA-256.

```powershell
git tag v1.0.0
git push origin v1.0.0
```

Un tag `v*` crée automatiquement une GitHub Release. L’exécutable n’est pas
signé numériquement : Windows SmartScreen peut afficher un avertissement jusqu’à
la mise en place d’un certificat de signature de code.

## Outils en ligne de commande

L’interface graphique est le parcours principal. Les scripts historiques restent
disponibles pour l’automatisation :

```powershell
# Extraire fidèlement une archive dans data/
python ./format_data.py ./bibliotheque-amiibo.zip

# Préparer puis synchroniser
python ./format_data.py ./bibliotheque-amiibo.zip --sync

# Synchroniser un dossier déjà préparé
python ./format_data.py --sync
```

La préparation conserve exactement les noms et l’arborescence contenus dans le
ZIP, à l’exception de son éventuel dossier racine commun. Elle n’applique aucun
alias, aucune suppression de préfixe et aucun raccourcissement.

## Documentation

- [Workflow de l’application](docs/APP_WORKFLOW.md)
- [Suivi du développement](docs/DEVELOPMENT_STATUS.md)
- [Protocole BLE Pixl.js](https://github.com/solosky/pixl.js/blob/main/docs/en/05%2B1-ble_protocol.md)
