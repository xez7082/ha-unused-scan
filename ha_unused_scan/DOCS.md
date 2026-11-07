# Nettoyeur de configuration

Ouvrez le module depuis le menu latéral (« Nettoyeur »), puis cliquez sur **Analyser**.

## Fichiers
Pour chaque fichier de `/config/packages/`, le module liste les entités qu'il crée et cherche
si elles sont citées ailleurs (autres fichiers YAML, tableaux de bord, tableau de bord Énergie,
pages HTML du dossier `www`, entités exposées à Alexa/Google).

- **Aucune entité citée ailleurs** : candidat à l'archivage.
- **Partiellement utilisé** : le fichier sert ; la partie inutilisée est listée à titre indicatif.

## Archiver / remettre
**Archiver** DÉPLACE le fichier dans `/config/_archive/` (rien n'est supprimé).
L'onglet **Archive** permet de le remettre à sa place. Après un archivage : cliquez sur
**Vérifier la configuration**, puis redémarrez Home Assistant.

## Automatisations
Jamais déclenchées, inactives depuis N jours (option `jours_inactifs`), désactivées, et entités
citées dans `automations.yaml` mais absentes ou indisponibles.

## Limites
Ce sont des **candidats** : un usage dynamique (nom d'entité construit dans un modèle) ou externe
à Home Assistant n'est pas détectable. Faites toujours une sauvegarde avant de nettoyer.


## Automatisations

Seules les automatisations créées dans l'interface (présentes dans `automations.yaml`) sont archivables.
L'archivage les retire de `automations.yaml`, les range dans `_archive/automations_archivees.yaml`
et recharge les automatisations. Une sauvegarde complète de `automations.yaml` est faite avant chaque changement.
Pour les remettre : onglet **Archive** → **Restaurer**.
