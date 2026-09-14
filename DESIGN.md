---
name: Allmiibo Manager
description: Un explorateur Windows calme qui place la bibliothèque de l'appareil au centre.
colors:
  graphite-canvas: "#0f1318"
  graphite-surface: "#151a20"
  graphite-raised: "#202832"
  graphite-control: "#222a33"
  graphite-control-hover: "#2a3540"
  graphite-tree: "#101419"
  graphite-border: "#34404b"
  text-primary: "#edf2f6"
  text-muted: "#99a4af"
  coral-import: "#e9785b"
  coral-import-hover: "#f18a6e"
  coral-ink: "#1a0c08"
  mint-status: "#58d6a5"
  mint-connected-surface: "#18392f"
  mint-connected-text: "#79e1b8"
  blue-search: "#68a8ff"
  blue-link: "#82b8ff"
  blue-guide: "#17233a"
typography:
  display:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "24px"
    fontWeight: 700
  brand:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "22px"
    fontWeight: 700
  title:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "14px"
    fontWeight: 650
  body:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "13px"
  label:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "13px"
    fontWeight: 600
rounded:
  menu: "5px"
  control: "7px"
  surface: "10px"
  chip: "11px"
  explorer: "12px"
spacing:
  toolbar: "4px"
  compact: "7px"
  control-y: "8px"
  surface: "10px"
  content: "14px"
  page-x: "24px"
components:
  button-import:
    backgroundColor: "{colors.coral-import}"
    textColor: "{colors.coral-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-import-hover:
    backgroundColor: "{colors.coral-import-hover}"
    textColor: "{colors.coral-ink}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-secondary:
    backgroundColor: "{colors.graphite-control}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  connection-chip:
    backgroundColor: "{colors.graphite-raised}"
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 10px"
  connection-chip-connected:
    backgroundColor: "{colors.mint-connected-surface}"
    textColor: "{colors.mint-connected-text}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 10px"
  guide-banner:
    backgroundColor: "{colors.blue-guide}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.surface}"
    padding: "10px 12px 10px 14px"
  explorer-panel:
    backgroundColor: "{colors.graphite-surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.explorer}"
---

# Design System: Allmiibo Manager

## Overview

**Creative North Star: "La Console Silencieuse"**

Allmiibo Manager est un explorateur d'appareil, pas un tableau de bord. L'appareil est l'espace de travail et les fichiers locaux ne sont que des entrées : l'arborescence distante garde donc la priorité visuelle, tandis que la connexion, les commandes et l'activité restent lisibles sans la concurrencer.

Le monde visuel est une utilité graphite calme, proche de la densité de l'Explorateur Windows. La menthe confirme la présence de l'appareil, le corail porte l'unique action d'import globale et le bleu guide la recherche ou l'aide. La narration reste stable : connecter, voir, modifier avec précision, puis confirmer.

**Key Characteristics:**

- L'appareil est toujours présenté comme la source de vérité.
- Les contrôles sont natifs, directs et compacts ; la zone de fichiers respire davantage.
- Une seule action corail domine la barre de commandes.
- Les états techniques sont traduits en confirmations ou instructions lisibles.
- L'illustration Bluetooth est vectorielle et discrètement animée pendant la recherche.

## Colors

La palette oppose un socle graphite peu saturé à trois accents strictement sémantiques : corail pour l'import, menthe pour la connexion ou la réussite, bleu pour la recherche et l'assistance.

### Primary

- **Corail d'import** (`coral-import`) : identifie exclusivement l'import ZIP et la relance principale sur l'écran de connexion.
- **Corail actif** (`coral-import-hover`) : confirme le survol de cette action prioritaire sans changer son sens.

### Secondary

- **Menthe de statut** (`mint-status`) : anime la présence de l'appareil et remplit la progression.
- **Menthe connectée** (`mint-connected-surface`, `mint-connected-text`) : compose le badge de connexion positive.

### Tertiary

- **Bleu de recherche** (`blue-search`) : porte le signal de recherche Bluetooth.
- **Bleu de lien** (`blue-link`) : distingue l'aide, le téléchargement et les détails repliables.
- **Bleu de guide** (`blue-guide`) : forme le bandeau d’accès au Drive et aux ressources firmware.

### Neutral

- **Graphite de toile** (`graphite-canvas`) : fond continu de l'application.
- **Graphite de surface** (`graphite-surface`) : activités et conteneurs secondaires.
- **Graphite élevé** (`graphite-raised`) : état de connexion neutre et corps de l'illustration.
- **Graphite de contrôle** (`graphite-control`, `graphite-control-hover`) : boutons utilitaires au repos et au survol.
- **Graphite d'arborescence** (`graphite-tree`) : surface sombre qui maximise la lisibilité des fichiers.
- **Bord graphite** (`graphite-border`) : séparation discrète des contrôles et menus.
- **Texte principal** (`text-primary`) : noms, titres et commandes actives.
- **Texte atténué** (`text-muted`) : sous-titres, capacité et métadonnées.

### Named Rules

**The Three Signals Rule.** Le corail signifie importer, la menthe signifie connecté ou réussi, et le bleu signifie rechercher, apprendre ou naviguer ; ne jamais échanger ces rôles.

**The One Coral Action Rule.** Une surface ne montre qu'une seule action corail prioritaire à la fois.

## Typography

**Display Font:** Segoe UI Variable (avec Segoe UI en repli)
**Body Font:** Segoe UI Variable (avec Segoe UI en repli)

**Character:** La pile système rend l'application immédiatement familière sous Windows et conserve une excellente lisibilité sans alourdir le paquet. La hiérarchie vient de la taille et du poids, jamais d'une seconde famille décorative.

### Hierarchy

- **Display** (`display`) : titre central de l'état de connexion.
- **Brand** (`brand`) : nom du produit dans l'en-tête persistant.
- **Title** (`title`) : titre de la bibliothèque et repères de section.
- **Body** (`body`) : commandes, lignes de fichiers, consignes et métadonnées courantes.
- **Label** (`label`) : badge de connexion et actions qui réclament une emphase compacte.

### Named Rules

**The Native Voice Rule.** Utiliser la pile Segoe UI existante et réserver les graisses fortes aux titres, au badge et à l'action principale.

## Layout

La fenêtre démarre sur un canevas de bureau de 1080 × 720 px et reste utilisable jusqu'à 720 × 520 px. Une marge horizontale de `page-x` encadre l'ensemble ; les grands blocs suivent le rythme `content`, tandis que les surfaces internes utilisent `surface` ou `compact` selon leur densité.

L'en-tête aligne l'identité à gauche et la capacité avec l'état de connexion à droite. Une fois connecté, le bandeau Drive et firmware, la barre de commandes, l'arborescence extensible et l'activité forment une colonne unique. L'arborescence absorbe toute hauteur disponible ; l'activité reste ancrée en bas.

En largeur réduite, les libellés des commandes restent visibles aussi longtemps que possible. Un bouton **Plus**, placé immédiatement après la dernière commande visible, range les actions restantes dans un menu au lieu de transformer toute l'interface en rangée d'icônes ambiguës.

**The Tree Owns the Space Rule.** Après la connexion, toute expansion verticale revient d'abord à l'arborescence distante.

## Elevation & Depth

Le système est plat par défaut. La profondeur vient de couches tonales — toile, surfaces, contrôles et arborescence — complétées par de fins contours sur l'explorateur et les commandes. Aucune ombre portée n'est définie dans l'interface actuelle.

**The Tonal Depth Rule.** Créer la hiérarchie par contraste de surface et bordure fine, jamais par une accumulation d'ombres.

## Shapes

Les formes sont doucement techniques : contrôles compacts avec `control`, bandeaux avec `surface`, badge d'état en capsule courte avec `chip`, et grand panneau de bibliothèque avec `explorer`. Les rayons restent assez contenus pour préserver le caractère d'outil Windows ; seul le dessin de l'appareil adopte une silhouette plus arrondie.

## Components

### Buttons

- **Shape:** contrôles compacts à coins modérément arrondis (`control`).
- **Primary:** `button-import` réserve le corail et l'encre sombre à l'import ZIP ou à la relance principale.
- **Hover / Focus:** `button-import-hover` intensifie le corail ; les commandes neutres passent de `graphite-control` à `graphite-control-hover` et conservent un contour lisible.
- **Secondary / Link:** les commandes ordinaires restent graphite ; les actions d'aide sont sans fond ni bordure et utilisent `blue-link`.
- **Disabled:** le contrôle reste visible mais recule fortement dans la hiérarchie jusqu'au retour d'une connexion ou à la fin de l'opération.

### Chips

- **Style:** `connection-chip` porte l'attente ou la déconnexion ; `connection-chip-connected` associe un point d'état et le nom réel de l'appareil.
- **State:** le changement de fond et de texte suffit ; ne pas ajouter un second badge pour la même connexion.

### Cards / Containers

- **Corner Style:** `surface` pour le guide et l'activité ; `explorer` pour la bibliothèque dominante.
- **Background:** `guide-banner` oriente vers la mise à jour officielle ; `explorer-panel` contient l'arborescence distante.
- **Shadow Strategy:** aucune ombre ; voir la règle de profondeur tonale.
- **Border:** le panneau d'exploration reçoit une bordure graphite, l'activité s'en passe.
- **Internal Padding:** les bandeaux emploient principalement `surface` sur l'axe vertical et `content` sur l'axe horizontal.

### Navigation

Il n'existe pas de navigation applicative persistante. Le passage connexion → bibliothèque se fait automatiquement, et les liens bleus ouvrent uniquement l'aide ou les détails. La barre d'actions conserve ses libellés puis place les commandes excédentaires dans le bouton **Plus** inline lorsque la largeur manque.

### Arborescence de bibliothèque

La bibliothèque est le composant signature : lignes de 28 px minimum, colonne de sélection compacte suivie de Nom / Type / Taille, alternance tonale légère, survol sombre et sélection menthe profonde. La case d’en-tête sélectionne tous les fichiers et dossiers supprimables et reflète les états aucun, partiel ou complet. `fav`, `data` et leurs parents conservent une case visible mais désactivée. L’indentation et les contrôles d’expansion appartiennent exclusivement à la colonne Nom ; les cases restent alignées sur un axe fixe à toutes les profondeurs. Le dépôt et le menu contextuel sélectionnent d’abord la cible visuelle afin que la destination active reste explicite. Un clic dans le vide réactive le libellé menthe **Bibliothèque** et la destination racine.

### Activité et progression

Le panneau inférieur affiche un résumé permanent, une barre menthe temporaire et un journal repliable. Une suppression y expose ses cibles et ses totaux fichiers/dossiers ; un import y sépare l’extraction du ZIP de la synchronisation BLE. Une confirmation réussie reste visible cinq secondes ; les erreurs expliquent la récupération attendue et réservent les détails techniques au journal.

## Do's and Don'ts

### Do:

- **Do** laisser l'arborescence occuper l'essentiel de l'espace connecté.
- **Do** afficher la destination avant un envoi et conserver une preuve de l'opération dans l'activité.
- **Do** employer le libellé complet d'une action tant que la barre d'outils peut l'accueillir.
- **Do** traduire les états Bluetooth en une instruction utilisateur et garder le diagnostic brut dans les détails.
- **Do** conserver une case visible mais désactivée pour `fav`, `data` et leurs parents.
- **Do** maintenir le triptyque connecter, voir, modifier, confirmer dans toute nouvelle surface.

### Don't:

- **Don't** présenter les chemins internes, lettres de disque ou fichiers temporaires comme des concepts utilisateur.
- **Don't** multiplier les cartes, badges ou couleurs d'accent autour de l'arborescence.
- **Don't** utiliser le corail pour une action destructive ou secondaire.
- **Don't** remplacer en mode compact tous les libellés par des icônes seules.
- **Don't** ajouter des ombres décoratives à des surfaces déjà distinguées tonalement.
- **Don't** proposer une suppression ou un renommage qui permettrait de contourner la protection de `fav` ou `data`.
