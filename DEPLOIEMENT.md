# Mise en ligne sur Oracle Cloud (offre « Always Free »)

Objectif : l'application accessible sur `https://<votre-nom>.duckdns.org`, protégée par mot de passe, avec sauvegarde quotidienne.
Durée : environ 1 h 30 la première fois.

> **Limites à connaître avant de commencer**
> - Les menus d'Oracle changent : si un nom diffère légèrement, cherchez l'équivalent.
> - Oracle **peut reprendre** un serveur gratuit peu utilisé (processeur, réseau et mémoire sous 20 % pendant 7 jours). Les sauvegardes (étape 9) sont là pour ça.
> - Les fichiers de ce guide (`setup_vm.sh`, `docker-compose.prod.yml`, `Caddyfile`) ont été vérifiés pour leur syntaxe mais **n'ont pas encore tourné sur un serveur Oracle** : la première installation est un test.
> - **Pas de vraies factures avant d'avoir réussi le test de restauration (étape 10).**
> - Données d'entreprise : voir la loi 09-08 / CNDP avant de charger des factures réelles.

## 1. Créer le compte Oracle Cloud
1. Aller sur oracle.com/cloud/free et créer un compte « Free Tier ».
2. Choisir la **région d'attache (home region)** avec soin : elle ne peut plus être changée, et le serveur gratuit ne peut être créé que dans cette région. Prendre une région européenne proche.
3. Une vérification par carte bancaire est possible à l'inscription (non confirmé par la documentation).

## 2. Créer le serveur
Menu **Compute → Instances → Create instance** :
- **Image** : Canonical Ubuntu 24.04 (ou 22.04).
- **Shape** : Ampere (processeur ARM), `VM.Standard.A1.Flex`, **2 OCPU et 12 Go** de mémoire. Attention à bien choisir une forme marquée « Always Free-eligible ».
- **Réseau** : laisser un réseau public avec une **adresse IP publique** attribuée.
- **Clé SSH** : choisir « Generate a key pair » et **télécharger la clé privée** (`.key`). Gardez-la précieusement, elle ne sera plus proposée.
- Si le message « Out of host capacity » apparaît, réessayer plus tard ou changer de domaine de disponibilité.

Notez l'**adresse IP publique** du serveur.

## 3. Ouvrir le web (ports 80 et 443) chez Oracle
Menu **Networking → Virtual cloud networks →** votre réseau **→ Security lists →** liste par défaut **→ Add ingress rules** :
- Source CIDR `0.0.0.0/0`, protocole TCP, port de destination `80`.
- Une seconde règle identique pour le port `443`.

(Le port 22 pour SSH est déjà ouvert par défaut.)

## 4. Obtenir un nom de domaine gratuit
Le certificat HTTPS demande un nom, pas une simple adresse IP.
1. Créer un compte sur **duckdns.org** (gratuit) et un sous-domaine, par exemple `tva-hamza`.
2. Dans le champ « current ip », saisir l'adresse IP du serveur.
3. Le nom obtenu est `tva-hamza.duckdns.org`. (Vérifier que le service est toujours gratuit au moment de l'inscription ; sinon tout nom de domaine que vous possédez convient.)

## 5. Se connecter au serveur (depuis PowerShell sur votre ordinateur)
```powershell
ssh -i C:\chemin\vers\ssh-key.key ubuntu@ADRESSE_IP
```
Si Windows refuse la clé pour permissions trop ouvertes : clic droit sur le fichier → Propriétés → Sécurité → Avancé → retirer les autres utilisateurs.

## 6. Installer Docker et ouvrir le pare-feu du serveur
Sur le serveur :
```bash
sudo apt-get update && sudo apt-get install -y git
```
Récupérer le projet. **Si le dépôt GitHub est public** :
```bash
git clone https://github.com/Ferdaousse24/tva-control.git
```
**S'il est privé**, créer une clé de lecture :
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
Copier la ligne affichée dans GitHub → dépôt → Settings → **Deploy keys → Add deploy key** (laisser « Allow write access » décoché), puis :
```bash
git clone git@github.com:Ferdaousse24/tva-control.git
```
Ensuite :
```bash
cd tva-control
bash scripts/setup_vm.sh
```
Quand c'est terminé : `exit`, puis se **reconnecter** en SSH (nécessaire pour que Docker soit utilisable sans `sudo`).

## 7. Configurer
```bash
cd tva-control
cp env.prod.example .env
nano .env
```
Remplir `DOMAIN` (votre nom DuckDNS), `POSTGRES_PASSWORD` et `APP_PASSWORD` (mots de passe **longs et différents**). Enregistrer : `Ctrl+O`, `Entrée`, `Ctrl+X`. Le fichier `.env` ne doit jamais aller sur GitHub (il est déjà ignoré par Git).

## 8. Lancer
```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```
La première fois, la construction prend plusieurs minutes. Vérifier :
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail 30 caddy
```
Puis ouvrir `https://VOTRE-NOM.duckdns.org` : le navigateur demande l'identifiant (`APP_USER`, par défaut `hamza`) et le mot de passe. Cliquer sur « Commencer avec le trimestre en cours » (ne pas charger la démonstration avec de vraies données).

Si le certificat n'est pas obtenu : vérifier que le nom pointe bien vers l'IP (`nslookup VOTRE-NOM.duckdns.org`) et que les ports 80 et 443 sont ouverts aux **deux** endroits (étapes 3 et 6).

## 9. Sauvegarde automatique (chaque nuit à 2 h)
```bash
mkdir -p ~/tva-control/backups
crontab -e
```
Ajouter à la fin (choisir `nano` si demandé) :
```
0 2 * * * cd $HOME/tva-control && ./scripts/backup_prod.sh >> backups/backup.log 2>&1
```
Tester tout de suite : `./scripts/backup_prod.sh` doit afficher « sauvegarde OK ».

**Copie hors du serveur** (indispensable : une sauvegarde sur le même serveur ne protège pas d'une reprise par Oracle). Depuis PowerShell sur votre ordinateur, une fois par semaine :
```powershell
scp -i C:\chemin\vers\ssh-key.key -r ubuntu@ADRESSE_IP:tva-control/backups C:\Users\ADMIN\Documents\sauvegardes-tva
```

## 10. Test de restauration (obligatoire avant les vraies données)
Sur le serveur, en remplaçant la date par celle d'un fichier de `backups/` :
```bash
cd ~/tva-control
docker compose -f docker-compose.prod.yml --env-file .env exec -T db psql -U tva -d postgres -c "DROP DATABASE IF EXISTS test_restore" -c "CREATE DATABASE test_restore"
gunzip -c backups/base-AAAAMMJJ-HHMM.sql.gz | docker compose -f docker-compose.prod.yml --env-file .env exec -T db psql -U tva -d test_restore -q
docker compose -f docker-compose.prod.yml --env-file .env exec -T db psql -U tva -d test_restore -c "select count(*) from invoices"
docker compose -f docker-compose.prod.yml --env-file .env exec -T db psql -U tva -d postgres -c "DROP DATABASE test_restore"
```
Le nombre de factures doit correspondre à celui de l'application. Les fichiers de factures se restaurent avec :
`docker compose -f docker-compose.prod.yml --env-file .env exec -T app tar -C /data -xzf - < backups/factures-AAAAMMJJ-HHMM.tar.gz`

## Mise à jour de l'application
Sur votre ordinateur : `git push`. Sur le serveur :
```bash
cd ~/tva-control && git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## Dépannage rapide
| Symptôme | À regarder |
|---|---|
| Le site ne répond pas | `docker compose -f docker-compose.prod.yml ps` : les 3 services doivent être « running » |
| Erreur de certificat | Étape 4 (nom → IP) et ports 80/443 ouverts chez Oracle **et** sur le serveur |
| « variable is missing » au lancement | Il manque une valeur dans `.env` |
| Photos non lues | `docker compose -f docker-compose.prod.yml logs app` ; Tesseract est installé dans l'image |
| Serveur injoignable pendant des jours | Il a peut-être été repris par Oracle : recréer le serveur (étapes 2 à 8) puis restaurer la dernière sauvegarde copiée sur votre ordinateur |
