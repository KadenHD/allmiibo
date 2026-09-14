# Workflow de l’application

## Objectif

Allmiibo Manager masque le protocole BLE, les lettres de disque et les dossiers
internes. L’utilisateur gère uniquement sa bibliothèque d’amiibos.

## Parcours principal

1. L’application démarre et recherche automatiquement un Allmiibo/Pixl.js en
   mode **Bluetooth Transmission**.
2. Après connexion, elle garde la session BLE ouverte et affiche la bibliothèque
   distante sous forme d’arborescence.
3. L’utilisateur peut ajouter des fichiers `.bin`, ajouter un dossier, créer,
   renommer ou supprimer un élément, puis actualiser la bibliothèque.
4. L’import automatique accepte le ZIP téléchargé depuis le dossier Google
   Drive indiqué dans l’application. L’archive est extraite fidèlement dans le
   dossier temporaire Windows, synchronisée, puis supprimée automatiquement.
5. Pendant l’import : contenu identique ignoré, contenu différent remplacé,
   nouveau contenu ajouté. Les fichiers distants absents du ZIP sont conservés.
6. La connexion est surveillée tant que l’application reste ouverte. Une erreur
   ramène vers un écran de reconnexion sans exposer les détails du protocole ;
   les tentatives reprennent automatiquement toutes les 4 à 30 secondes.
7. L’en-tête affiche l’espace disponible recalculé après chaque actualisation ou
   opération. Un glisser-déposer sélectionne le dossier réellement survolé et
   annonce sa destination dans la zone d’activité.
8. La première colonne permet de cocher plusieurs fichiers et dossiers. Sa case
   d’en-tête sélectionne ou désélectionne tous les éléments autorisés, le bouton de
   suppression indique leur nombre et une confirmation récapitule les cibles.
   Seule la colonne **Nom** porte l’indentation des sous-dossiers afin que les
   cases restent toujours alignées et visibles.
9. Le bandeau d’aide rappelle que Kirby Air Riders nécessite Pixl.js 2.16+ et
   fournit un accès direct à l’outil DFU ainsi qu’aux releases du firmware.
10. Un clic dans le vide de l’arborescence sélectionne la racine
    **Bibliothèque**. Les ajouts suivants ne réutilisent donc jamais
    silencieusement le dernier dossier sélectionné.
11. En largeur réduite, un bouton **Plus** suit immédiatement les actions encore
    visibles et contient uniquement celles qui ne tiennent plus sur la ligne.
12. La fenêtre peut être fermée immédiatement depuis l’écran initial : une
    recherche BLE active est annulée sans attendre son délai d’expiration ni la
    prochaine tentative automatique.

## Règles de sécurité

- Toutes les opérations visibles sont limitées à la bibliothèque `amiibo`.
- La suppression de la racine est interdite.
- Les dossiers `fav` et `data` ne peuvent jamais être supprimés ou renommés.
  Tout dossier parent qui les contient est également exclu d’une suppression
  récursive.
- Une suppression manuelle demande toujours confirmation.
- Un même répertoire ne peut pas contenir deux dossiers de même nom, même si
  seule la casse diffère.
- Le renommage d’un amiibo ne rend jamais son extension `.bin` modifiable.
- Le remplacement d’un fichier passe par une copie temporaire vérifiée avec
  restauration de l’original si l’opération échoue.
- Aucun ZIP ni fichier importé n’est conservé par l’application.
- Aucun nom n’est réécrit : pas d’alias, de suppression de préfixe ou de
  raccourcissement automatique. Un chemin manuel incompatible avec le protocole
  est refusé explicitement avant l’envoi.
- Les détails d’import séparent la préparation du ZIP de la synchronisation BLE ;
  ceux d’une suppression donnent les cibles et les totaux de fichiers et dossiers.

## Décision encore ouverte

L’import ZIP fonctionne comme une mise à jour fusionnée et conserve les fichiers
présents uniquement sur l’appareil. Un futur mode « miroir exact » pourrait les
supprimer, mais devra être séparé et accompagné d’une confirmation forte.
