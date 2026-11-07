# Changelog

## 1.0.2
- La page du module n'est plus mise en cache par le navigateur : une mise à jour s'affiche tout de suite (plus besoin de vider le cache).

## 1.0.1
- Recherche corrigée : elle cherche maintenant dans tous les fichiers et toutes les automatisations (plus seulement dans le filtre actif), sans tenir compte des accents ni des majuscules, avec plusieurs mots et des espaces.
- Compteur de résultats affiché pendant la recherche.

## 1.0.0
- Nouvelle interface : synthèse chiffrée, recherche, filtres, fenêtre de confirmation, thème sombre/clair, export du rapport (Markdown).
- Analyse plus poussée : verdict Sûr / Probable / À vérifier, détection des alertes, automatisations et scripts contenus dans un fichier, état réel des entités, fichiers cités seulement par d'autres candidats.
- Archivage réversible des automatisations (sauvegarde complète de automations.yaml avant chaque changement, rechargement automatique).
- Icône, logo, traduction française des options.

## 0.1.0
- Première version : analyse des fichiers `packages/*.yaml`, archivage réversible dans `_archive`, vérification de la configuration.
