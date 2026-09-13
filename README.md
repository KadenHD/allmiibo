# Allmiibo

Outils Python pour préparer une archive d'amiibos puis synchroniser les fichiers
`.bin` avec un Allmiibo/Pixl.js par Bluetooth Low Energy (BLE).

- [Site Allmiibo](https://allmiibo.com/)
- [Téléchargement des données](https://allmiibo.com/support/) : télécharger le
  « Data file »
- [Gestionnaire Web Bluetooth](https://bt.allmiibo.com/) : connecter le Pixl.js,
  créer les dossiers et envoyer manuellement des fichiers

## Prérequis

- Python 3.10 ou plus récent
- Un Allmiibo/Pixl.js en mode **Bluetooth Transmission** pour la synchronisation

Installer la dépendance BLE :

```powershell
python -m pip install -r ./requirements.txt
```

## Préparer les données

`format_data.py` extrait l'archive dans `data/`, retire son éventuel dossier
racine commun et génère directement les noms définitifs qui seront utilisés sur
l'Allmiibo.

```powershell
python ./format_data.py ./amiiboall0630.zip
```

Le formatage normalise notamment les conventions suivantes :

```text
[AC] 001 - Isabelle.bin          -> Isabelle.bin
SSB_90_-_Sephiroth.bin          -> Sephiroth.bin
[YU-GI-OH] Yuga Oudou.bin       -> Yuga Oudou.bin
MHR_Palamute_Canyne_Malzeno.bin -> Palamute Canyne Malzeno.bin
08-Solaire of Astora.bin        -> Solaire of Astora.bin
```

Les dossiers trop longs utilisent des alias lisibles, par exemple `Zelda`,
`BOTW`, `MH Rise`, `Power Pros` ou `Welcome amiibo`. Aucun identifiant artificiel
ou suffixe généré à partir d'un hash n'est ajouté. En cas de véritable collision
entre deux fichiers différents, le second reçoit un suffixe lisible comme `(2)`.

Les noms sont produits en respectant les limites de l'appareil :

- chemin complet : 63 octets UTF-8 maximum ;
- nom de fichier ou de dossier : 47 octets UTF-8 maximum.

Par défaut, un fichier local déjà présent est :

- ignoré si son contenu est identique ;
- remplacé si son contenu est différent.

Une nouvelle préparation nettoie aussi les anciens chemins générés par une
version précédente du script, uniquement lorsque leur contenu correspond encore
exactement à celui de l'archive. Un fichier modifié manuellement est conservé.

Politiques de conflit disponibles :

```powershell
python ./format_data.py ./amiiboall0630.zip --conflict error
python ./format_data.py ./amiiboall0630.zip --conflict skip
python ./format_data.py ./amiiboall0630.zip --conflict overwrite
python ./format_data.py ./amiiboall0630.zip --conflict rename
```

Autres options utiles :

```powershell
# Prévisualiser sans modifier data/
python ./format_data.py ./amiiboall0630.zip --dry-run

# Conserver le dossier racine commun de l'archive
python ./format_data.py ./amiiboall0630.zip --keep-root

# Afficher chaque chemin traité à la place de la barre de progression
python ./format_data.py ./amiiboall0630.zip -v
```

## Synchroniser avec l'Allmiibo

Avant de lancer la synchronisation :

1. placer l'Allmiibo/Pixl.js en mode **Bluetooth Transmission** ;
2. fermer le gestionnaire Web s'il est déjà connecté à l'appareil ;
3. garder l'appareil à proximité de l'ordinateur.

Pour préparer l'archive puis synchroniser immédiatement :

```powershell
python ./format_data.py ./amiiboall0630.zip --sync
```

Pour synchroniser un dossier `data/` déjà préparé :

```powershell
python ./format_data.py --sync
```

Le script choisit `E:/amiibo` si le disque `E:` est disponible, sinon
`I:/amiibo`. Il ne synchronise que les fichiers `.bin` et ne renomme rien au
moment de l'envoi : les noms présents dans `data/` sont les noms définitifs.

Pendant la synchronisation :

- un fichier distant identique est lu, comparé puis ignoré ;
- un fichier absent est envoyé ;
- un fichier différent est remplacé de manière sécurisée avec vérification et
  restauration en cas d'échec ;
- les fichiers présents uniquement sur l'appareil sont conservés ;
- aucun fichier système ou élément situé hors du dossier cible n'est modifié.

Une barre affiche l'avancement et l'action courante :

```text
[████████████░░░░░░░░░░░░░░░░] 327/746 envoyé
```

Utiliser le mode détaillé pour afficher les chemins un par un :

```powershell
python ./format_data.py --sync -v
```

Options de synchronisation utiles :

```powershell
# Simuler les opérations BLE sans écrire sur l'appareil
python ./format_data.py --sync --dry-run -v

# Forcer le disque, le dossier distant et l'appareil
python ./format_data.py --sync --drive E --device-root amiibo --device Pixl.js

# Modifier les délais BLE
python ./format_data.py --sync --scan-timeout 20 --response-timeout 30
```

> `--dry-run` ne peut pas être combiné en une seule commande avec une archive et
> `--sync`. Préparer d'abord `data/`, puis lancer séparément la simulation BLE.

## Pourquoi l'envoi est-il lent ?

Un premier envoi complet peut prendre environ 45 à 60 minutes. Le protocole BLE
transfère les fichiers par petits blocs et le script effectue des opérations
séquentielles ainsi qu'une vérification après écriture. Une synchronisation
suivante évite de réécrire les fichiers identiques, mais doit tout de même les
lire pour comparer leur contenu.

## Aide

```powershell
python ./format_data.py --help
```

Protocole utilisé : [documentation BLE de Pixl.js](https://github.com/solosky/pixl.js/blob/main/docs/en/05%2B1-ble_protocol.md).
