# Mise en ligne gratuite, sans carte bancaire : Supabase + Render

Architecture : **Supabase** garde les données (base PostgreSQL), **Render** fait tourner l'application complète (écrans + serveur). Les fichiers PDF/photos sont copiés dans la base, donc rien n'est perdu quand Render redémarre.

> Limites à connaître : l'offre gratuite de Render s'endort après ~15 min sans visite (premier chargement lent, ~1 min). Supabase gratuit se met en pause après ~1 semaine sans usage (se réactive depuis son tableau de bord). Ces offres peuvent changer : vérifier à l'inscription.
> Données fictives uniquement tant que Hamza n'a pas donné son accord (hébergement à l'étranger, loi 09-08).

## 1. Envoyer le code sur GitHub
```powershell
git add .
git commit -m "Prépare la mise en ligne Render + Supabase"
git push
```

## 2. Créer la base sur Supabase
1. supabase.com → **Start your project** → connexion avec GitHub.
2. **New project** : nom `tva-controle`, **région Europe** (ex. Frankfurt/Paris), choisir un mot de passe de base **simple, sans caractères spéciaux** (lettres et chiffres). Le noter.
3. Attendre la fin de la création (1–2 min).
4. Bouton **Connect** (en haut) → onglet **Session pooler** (important : compatible avec Render) → copier l'adresse `postgresql://postgres.xxxx:[YOUR-PASSWORD]@...:5432/postgres`.
5. Remplacer `[YOUR-PASSWORD]` par le mot de passe choisi (sans les crochets).

## 3. Créer le service sur Render
1. render.com → connexion avec GitHub.
2. **New +** → **Blueprint** → choisir le dépôt `tva-control` (Render lit `render.yaml`).
3. Il demande 3 valeurs :
   - `DATABASE_URL` : l'adresse Supabase de l'étape 2
   - `APP_PASSWORD` : le mot de passe d'accès de Hamza
   - `COMPANY_ICE` : l'ICE de l'entreprise
4. **Apply** et attendre la compilation (5–10 min la première fois).
5. Render donne une adresse `https://tva-controle-xxxx.onrender.com` (HTTPS inclus). Identifiant : `hamza`.

## 4. Vérifier
- Ouvrir l'adresse, saisir identifiant + mot de passe.
- Charger la démonstration, importer un PDF, ouvrir sa visionneuse.
- Dans Render → **Manual Deploy** (redémarrage) puis rouvrir la facture : elle doit toujours s'afficher.

## 5. Sauvegarde
Depuis ton PC, avec l'adresse Supabase (étape 2) :
```powershell
pg_dump "ADRESSE_SUPABASE" -f sauvegarde.sql
```
(nécessite PostgreSQL client installé). À faire chaque semaine, et avant tout vrai usage. Tester une restauration avant d'y mettre de vraies données.

## 6. Mises à jour
`git push` → Render recompile tout seul.

## En cas de problème
- **Build échoue** : copier les dernières lignes du journal Render.
- **« Connection refused / network unreachable »** : l'adresse n'est pas celle du *Session pooler*.
- **« password authentication failed »** : mot de passe mal recopié dans l'adresse.
- **Page blanche longue** : le service se réveille, attendre 1 minute.
