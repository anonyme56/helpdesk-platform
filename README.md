# Helpdesk : application cloud-native (projet BC3)

Gestion de tickets de support : front React, API FastAPI, worker RQ (mails et exports CSV), PostgreSQL, Redis et
stockage objet compatible S3. Le rapport complet est dans `../Rapport_Projet3_Cloud.pdf`.

Ce fichier explique comment tout lancer en local et comment accéder aux applications. Il y a deux façons de faire :

| | Mode A : docker compose | Mode B : Kubernetes (kind) |
|---|---|---|
| Pour quoi faire | voir l'appli tourner, la tester | voir toute la chaîne (Ingress HTTPS, autoscaling, supervision, sauvegardes) |
| Durée de mise en route | 3 à 5 minutes | 15 à 25 minutes la première fois (téléchargement des images) |
| Mémoire | environ 1,5 Go | 5 à 6 Go (Docker Desktop doit avoir au moins 7 Go alloués) |

Toutes les commandes sont à lancer depuis un terminal **Git Bash** (celui de VS Code convient), dans le dossier
`projet 3/helpdesk-platform`.

---

## 0. Prérequis

- **Docker Desktop** démarré (icône verte), avec au moins 7 Go de mémoire alloués (Settings > Resources).
- **Git Bash** et **Python 3** (pour les scripts de test).
- Mode B seulement : **kubectl** (fourni avec Docker Desktop) et **Terraform** 1.6 ou plus.
  Terraform n'est pas installé de base. Téléchargement : https://developer.hashicorp.com/terraform/install
  (version Windows amd64, dézippée n'importe où). Pour cette machine, il est déjà dans `~/p3-tools/bin` :

      export PATH="$HOME/p3-tools/bin:$PATH"

- Sous Windows, si une commande `npm` échoue avec `ERR_INVALID_ARG_TYPE`, lancer d'abord :

      export COMSPEC='C:\Windows\System32\cmd.exe'

- Sur cette machine la commande `docker compose` (avec un espace) n'est pas reconnue : utiliser **`docker-compose`**
  (avec un tiret).

---

## Mode A : docker compose

### 1. Lancer

    bash scripts/gen-env.sh            # crée le fichier .env avec des mots de passe aléatoires (une seule fois)
    docker-compose up -d --build       # construit les images et démarre tout

Au premier lancement la construction prend quelques minutes. Pour vérifier :

    docker-compose ps                  # les 7 services doivent être "healthy" (le worker n'a pas de sonde)

### 2. Accéder aux applications

| Quoi | Adresse | Identifiants |
|---|---|---|
| **Application** (front) | http://localhost:8081 | voir ci-dessous |
| **API** (documentation Swagger) | http://localhost:8000/docs | |
| **Mails envoyés par l'appli** (Mailpit) | http://localhost:8025 | aucun |

Compte administrateur : `admin@helpdesk.example.com`, mot de passe = la valeur `ADMIN_PASSWORD` du fichier `.env` :

    grep ADMIN_PASSWORD .env

Vous pouvez aussi créer votre propre compte avec « S'inscrire » sur la page de connexion (mot de passe de 10
caractères minimum). Un compte créé ainsi est un simple utilisateur : il ne voit que ses tickets. Pour tester le
rôle agent (voir tous les tickets, assigner, exporter), utilisez le compte administrateur.

### 3. Jeu de données de démonstration et test complet

    # remplit l'appli avec 3 utilisateurs et 8 tickets (mot de passe des comptes de démo : à choisir)
    PW=$(grep ADMIN_PASSWORD .env | cut -d= -f2)
    python scripts/seed.py --base-url http://localhost:8081 --admin-password "$PW" --demo-password "Demo-Helpdesk-2026"

    # test de bout en bout : compte, ticket, pièce jointe, export CSV par le worker, mail reçu
    python scripts/smoke_test.py --base-url http://localhost:8081 --admin-password "$PW" --mailpit-url http://localhost:8025

Après le jeu de démo, ces comptes existent (mot de passe `Demo-Helpdesk-2026` si vous gardez la même valeur) :
`alice.martin@example.com`, `karim.benali@example.com` (utilisateurs) et `sophie.durand@example.com` (agent).

Dans l'application : créer un ticket, l'ouvrir, joindre un fichier (png, jpeg, pdf ou txt, 5 Mo maximum), commenter.
Connecté en admin, « Exporter en CSV » lance une tâche de fond : le fichier se télécharge quand le worker a terminé.
Chaque création ou assignation de ticket envoie un mail visible dans Mailpit.

### 4. Arrêter

    docker-compose stop                # met en pause (les données sont conservées)
    docker-compose down                # supprime les conteneurs (données conservées)
    docker-compose down -v             # supprime aussi les données (base, fichiers)

---

## Mode B : Kubernetes en local (kind) avec Terraform

Terraform crée le cluster, le registre d'images, les secrets, le certificat HTTPS, l'Ingress et la supervision.
L'application est ensuite déployée avec un script.

### 1. Créer la plateforme

    cd terraform/local
    terraform init
    terraform apply                    # répondre "yes" ; compter 10 à 20 minutes la première fois
    cd ../..

Si le cluster existe déjà (c'est le cas sur cette machine, `terraform plan` doit afficher « No changes »),
cette étape n'est pas à refaire. Après un redémarrage de la machine, il suffit de relancer Docker Desktop : le
cluster et le registre redémarrent seuls. Vérification :

    kubectl get nodes                  # helpdesk-control-plane doit être "Ready"
    kubectl get pods -A                # tout doit être "Running" au bout de 2 à 3 minutes

Si le nœud n'apparaît pas : `docker start helpdesk-control-plane kind-registry`.

### 2. Déployer l'application

    scripts/deploy.sh dev  v1.1.0 --build      # construit les images, les pousse au registre, déploie dev
    scripts/deploy.sh prod v1.1.0              # même version en prod (images déjà construites)
    bash scripts/apply-monitoring.sh           # règles d'alerte et SLO (une seule fois)

Sans `--build`, le script réutilise des images déjà présentes dans le registre (`localhost:5001`). Il faut `--build`
pour une première installation depuis zéro. La construction des 4 images prend 3 à 8 minutes.

### 3. Accéder aux applications

Les noms `*.localtest.me` pointent automatiquement vers votre machine (127.0.0.1), aucune modification du fichier
`hosts` n'est nécessaire (il faut une connexion Internet pour la résolution DNS).

| Quoi | Adresse |
|---|---|
| **Application, environnement dev** | https://helpdesk-dev.localtest.me:8443 |
| **Application, environnement prod** | https://helpdesk.localtest.me:8443 |
| **Grafana** (tableau de bord) | https://grafana.localtest.me:8443 |
| **Prometheus** (métriques, alertes) | https://prometheus.localtest.me:8443 |
| **Alertmanager** | https://alertmanager.localtest.me:8443 |

Le port est **8443** (HTTPS) ; le port 8080 (HTTP) redirige vers lui.

**Avertissement du navigateur.** Le certificat est signé par une autorité interne créée par Terraform, donc le
navigateur affiche « connexion non sécurisée ». Cliquer sur « Avancé » puis « Continuer ». Pour ne plus avoir
l'avertissement, importer `terraform/local/.generated/ca.crt` comme autorité de confiance.

### 4. Identifiants

Les mots de passe sont générés par Terraform et stockés dans des Secrets Kubernetes (un jeu par environnement) :

    # administrateur de l'application (admin@helpdesk.example.com), dev puis prod
    kubectl -n helpdesk-dev  get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d; echo
    kubectl -n helpdesk-prod get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d; echo

    # Grafana (utilisateur : admin)
    cd terraform/local && terraform output -raw grafana_admin_password; echo; cd ../..

Dans Grafana : menu Dashboards > « Helpdesk - exploitation », puis choisir `helpdesk-prod` ou `helpdesk-dev` dans
la liste « Environnement » en haut à gauche. Prometheus et Alertmanager n'ont pas de mot de passe.

Les mails envoyés par l'application ne sont pas exposés par l'Ingress. Pour voir la boîte Mailpit d'un
environnement :

    kubectl -n helpdesk-prod port-forward svc/mailpit 8025:8025      # puis http://localhost:8025

### 5. Jeu de démonstration et test complet

    ADM=$(kubectl -n helpdesk-dev get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d)
    python scripts/seed.py --base-url https://helpdesk-dev.localtest.me:8443 --insecure \
        --admin-password "$ADM" --demo-password "Demo-Helpdesk-2026"
    python scripts/smoke_test.py --base-url https://helpdesk-dev.localtest.me:8443 --insecure --admin-password "$ADM"

(`--insecure` accepte le certificat interne.)

### 6. Essayer les fonctions d'exploitation

    # charge, pour voir l'autoscaler passer de 2 à 6 pods (dans un autre terminal : kubectl -n helpdesk-prod get hpa -w)
    python scripts/loadtest.py --base-url https://helpdesk.localtest.me:8443 --insecure \
        --email alice.martin@example.com --password "Demo-Helpdesk-2026" --duration 120 --concurrency 16

    # résilience : supprimer UN pod de l'API pendant que l'appli répond (Kubernetes en recrée un tout de suite)
    kubectl -n helpdesk-prod get pods -l app.kubernetes.io/name=backend
    kubectl -n helpdesk-prod delete pod <nom-d-un-pod-de-la-liste>

(ne pas supprimer tous les pods de l'API d'un coup avec un sélecteur : cela coupe le service le temps du redémarrage)

    # vérifier que les politiques réseau sont bien appliquées
    bash scripts/netpol-test.sh helpdesk-prod

    # sauvegarde manuelle de la base puis test de restauration dans une base séparée
    kubectl -n helpdesk-prod create job --from=cronjob/db-backup backup-test
    kubectl -n helpdesk-prod logs job/backup-test
    sed 's/NAMESPACE/helpdesk-prod/;s/TAG/v1.1.0/' k8s/ops/restore-job.yaml | kubectl apply -f -
    kubectl -n helpdesk-prod logs job/db-restore-test

### 7. Tout arrêter

    # libérer la mémoire sans rien perdre : arrêter les conteneurs du cluster
    docker stop helpdesk-control-plane kind-registry
    # (les relancer avec : docker start helpdesk-control-plane kind-registry)

    # tout supprimer (cluster, registre, secrets) : à faire seulement si vous n'en avez plus besoin
    cd terraform/local && terraform destroy

---

## Tests du code (sans rien démarrer)

    cd backend  && pip install -r requirements-dev.txt && pytest --cov=app && ruff check .
    cd worker   && pip install -r requirements-dev.txt && pytest tests
    cd frontend && npm ci && npm run lint && npm test && npm run build

## Dépannage rapide

| Symptôme | Cause probable et solution |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop n'est pas démarré ; attendre l'icône verte. |
| `docker compose` : commande inconnue | Utiliser `docker-compose` (avec un tiret). |
| `variable is not set` au lancement de compose | Le fichier `.env` manque : `bash scripts/gen-env.sh`. |
| Page blanche ou erreur 503 juste après le démarrage | Les services démarrent dans l'ordre ; attendre une minute et recharger. |
| Pods en `Pending` ou `Evicted`, Docker très lent | Mémoire insuffisante : fermer d'autres applications, ou arrêter l'environnement `dev` (`kubectl -n helpdesk-dev scale deploy,sts --all --replicas=0`). |
| `*.localtest.me` introuvable | Pas d'Internet ou DNS qui filtre ce domaine : ajouter les noms au fichier `C:\Windows\System32\drivers\etc\hosts` (`127.0.0.1 helpdesk.localtest.me helpdesk-dev.localtest.me grafana.localtest.me prometheus.localtest.me alertmanager.localtest.me`). |
| Après plusieurs mauvais mots de passe : erreur 429 | Protection anti force brute : attendre 5 minutes. |
| `terraform : command not found` | `export PATH="$HOME/p3-tools/bin:$PATH"` (ou installer Terraform). |

## Contenu du dépôt

| Dossier | Contenu |
|---|---|
| `backend/`, `worker/`, `frontend/`, `backup/` | code et Dockerfiles des 4 images |
| `docker-compose.yml` | la pile complète en local (mode A) |
| `k8s/base`, `k8s/overlays/{dev,test,prod}` | manifestes Kustomize ; `k8s/canary` (déploiement canary) et `k8s/ops` (test de restauration) |
| `terraform/local` | cluster kind, registre, secrets, TLS, Traefik, supervision (appliqué) |
| `terraform/aws` | cible AWS (VPC, EKS, RDS, S3, IAM, budget) : validé, **jamais appliqué** |
| `monitoring/` | règles d'alerte et SLO, générateur du tableau de bord Grafana |
| `.github/workflows/ci.yml` | pipeline CI/CD (non exécuté sur GitHub) |
| `docs/soa.md` | déclaration d'applicabilité ISO 27001 |
| `scripts/` | déploiement, tests de fumée, de charge, des politiques réseau, FinOps |

## À savoir

- Aucun secret dans le dépôt : `.env` et les secrets Kubernetes sont générés localement et ignorés par Git.
- Le stockage objet est SeaweedFS (les images officielles MinIO ne sont plus publiées) ; le code parle S3 standard.
- Limites assumées (pipeline non exécuté sur GitHub, module AWS non appliqué, reconstruction complète non rejouée,
  extinction automatique de dev non validée) : voir la section 10 du rapport.
