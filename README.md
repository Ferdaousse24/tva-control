# Contrôle de la TVA trimestrielle (Maroc)

Application web qui **lit** les factures (PDF, photo, scan), **calcule** la TVA du trimestre et la **compare** avec la déclaration du comptable.
Elle reprend les maquettes Figma « TVA-projet » : Import → Vérification → Calcul → Déclaration du comptable → Comparaison → Rapport.

> Version 1 de démonstration. Les règles de calcul sont dans `backend/app/tva.py`, les contrôles dans `backend/app/checks.py`.

## Lancer l'application

### Option A — Docker (le plus simple)
1. Installer Docker Desktop.
2. Dans le dossier du projet : copier `.env.example` en `.env` et changer les mots de passe.
3. `docker compose up --build`
4. Ouvrir http://localhost:8000 puis cliquer sur **Charger la démonstration**.

### Option B — Sans Docker (Windows)
Prérequis : Python 3.11+, Node 20+ (et Tesseract pour lire les photos, voir plus bas).

```powershell
# Serveur (base SQLite locale, aucun réglage)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Interface (dans un second terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

**Lire les photos et scans** demande Tesseract : installer « Tesseract OCR » pour Windows (version UB Mannheim), cocher la langue **French**, et ajouter son dossier au `PATH`. Les PDF avec texte fonctionnent sans lui.

## Parcours de démonstration (trimestre T2 2026)
1. **Tableau de board** : 11 factures, dont 1 « À vérifier » (`scan_0618.jpg`, une photo) et 1 non conforme (`achat_electro_0420.pdf`, ICE manquant).
2. Cliquer sur `scan_0618.jpg` : corriger si besoin, puis **Confirmer et valider**.
3. **TVA du trimestre** : 30 000 − 12 000 − crédit 1 000 = **17 000 MAD**. La TVA de la facture Electro Casa (1 200 MAD) est exclue.
4. **Comparer avec la déclaration déposée** : la déclaration du comptable (15 800 MAD) est déjà saisie ; modifiez-la si vous voulez.
5. **Comparaison** : écart de 1 200 MAD, origine = facture Electro Casa. **Générer le rapport** → PDF.
6. Essayez aussi : importer `samples/photo_vente_0614.jpg` (photo, deux taux de TVA), ou importer deux fois le même fichier (écran **Doublon détecté**).

## Tests
```
cd backend
python -m pytest -q
```
35 tests : formules de TVA, lecture des factures exemples, doublons, comparaison, rapport PDF, mot de passe.
Les factures exemples sont régénérables : `python scripts/make_samples.py`.

## Ce que fait / ne fait pas encore cette version
| Fait | Pas encore |
|---|---|
| Lecture PDF texte et photo/scan (OCR) avec score de confiance par champ | Lecture par modèle de vision (IA) : à brancher à la place de `extraction.interpret` après le test sur de vraies factures |
| Contrôles : ICE (15 chiffres), HT + TVA = TTC, taux autorisé à la date, mentions manquantes | Un seul paiement par facture (pas de paiements partiels répartis sur plusieurs dates) |
| Doublons (certain / probable), journal d'audit, validation humaine obligatoire | Retenue à la source opérée, régularisation du prorata sur immobilisations, avoirs |
| Fait générateur à l'encaissement, prorata, plafonds espèces, arrondi au dirham | Comptes utilisateurs (un seul mot de passe partagé pour l'instant) |
| Comparaison déclaré / recalculé, origine de l'écart, N-1, rapport PDF | Lecture automatique du PDF de la déclaration du comptable (saisie manuelle) |

## Mise en ligne
Voir **DEPLOIEMENT.md** (Oracle Cloud gratuit, HTTPS automatique, sauvegarde quotidienne).

## Avant toute mise en ligne
- Définir `APP_PASSWORD` (sinon l'application est ouverte à tous).
- Choisir un hébergement avec sauvegarde de la base (`scripts/backup.sh` fait une sauvegarde manuelle).
- Ne pas envoyer de vraies factures à un service d'IA externe sans l'accord du client (loi 09-08, déclaration CNDP).

## Structure
```
backend/   API FastAPI : tva.py (calculs), extraction.py (lecture), checks.py, duplicates.py, compare.py, report.py
frontend/  React + Vite : un fichier par écran dans src/pages
samples/   factures d'exemple (fictives) ; scripts/ : générateur, sauvegarde
```
