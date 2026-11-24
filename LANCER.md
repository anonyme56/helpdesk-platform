# Lancer le projet en local : version rapide

Tout se tape dans **Git Bash**, dans le dossier `projet 3/helpdesk-platform`.
Pre-requis : **Docker Desktop demarre** (icone verte).

---

## Option 1 : la plus simple (docker compose), 5 minutes

**1. Creer les mots de passe (une seule fois)**

    bash scripts/gen-env.sh

**2. Demarrer**

    docker-compose up -d --build

(attention : `docker-compose` avec un tiret. La premiere fois, compter quelques minutes.)

**3. Ouvrir dans le navigateur**

| Quoi | Adresse |
|---|---|
| Application | http://localhost:8081 |
| Mails envoyes par l'appli | http://localhost:8025 |
| API (documentation) | http://localhost:8000/docs |

**4. Se connecter**

- Email : `admin@helpdesk.example.com`
- Mot de passe : voir le resultat de

      grep ADMIN_PASSWORD .env

  (c'est ce qu'il y a apres le `=`)

Ou cliquer sur "S'inscrire" pour creer un compte simple.

**5. Remplir avec des donnees de demo (facultatif)**

    PW=$(grep ADMIN_PASSWORD .env | cut -d= -f2)
    python scripts/seed.py --base-url http://localhost:8081 --admin-password "$PW" --demo-password "Demo-Helpdesk-2026"

**6. Arreter**

    docker-compose stop        # pause, on garde les donnees
    docker-compose down -v     # tout supprimer, donnees comprises

---

## Option 2 : version Kubernetes (cluster deja installe sur cette machine)

**1. Verifier que le cluster tourne**

    kubectl get nodes

Si ca ne repond pas (ou si le noeud n'est pas `Ready`) :

    docker start helpdesk-control-plane kind-registry

puis attendre 2 a 3 minutes et refaire `kubectl get pods -A`.

**2. Ouvrir dans le navigateur** (accepter l'avertissement de certificat : "Avance" puis "Continuer")

| Quoi | Adresse |
|---|---|
| Application (dev) | https://helpdesk-dev.localtest.me:8443 |
| Application (prod) | https://helpdesk.localtest.me:8443 |
| Grafana (tableau de bord) | https://grafana.localtest.me:8443 |
| Prometheus | https://prometheus.localtest.me:8443 |
| Alertmanager | https://alertmanager.localtest.me:8443 |

**3. Recuperer les mots de passe**

Admin de l'appli (email `admin@helpdesk.example.com`) :

    kubectl -n helpdesk-prod get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d; echo

(remplacer `helpdesk-prod` par `helpdesk-dev` pour l'environnement dev)

Grafana (utilisateur `admin`) :

    export PATH="$HOME/p3-tools/bin:$PATH"
    cd terraform/local && terraform output -raw grafana_admin_password; echo; cd ../..

Dans Grafana : menu **Dashboards**, puis **"Helpdesk - exploitation"**.

**4. Liberer la memoire quand on a fini**

    docker stop helpdesk-control-plane kind-registry

---

## Le pipeline CI/CD (fichier `.github/workflows/ci.yml`)

Le fichier est valide : `actionlint` ne trouve aucune erreur. Un probleme a ete corrige : les scripts du
dossier `scripts/` n'avaient pas le droit d'execution dans Git, donc `scripts/deploy.sh` aurait echoue
("Permission denied") sur un runner Linux. Le formatage Terraform exige par la CI passe aussi.

**Important : ce pipeline n'a jamais tourne sur GitHub** (le depot n'a pas ete publie). Les etapes de qualite ont
ete executees a la main, dans les memes outils, mais pas par GitHub Actions. A ne pas presenter comme "teste sur
GitHub".

Ce que fait le pipeline :

| Job | Role | Remarque |
|---|---|---|
| backend, worker, frontend | lint, tests, audit des dependances | voir "audits" ci-dessous |
| secrets | detection de secrets (gitleaks) sur tout l'historique | |
| iac | Terraform (fmt, validate), scan Trivy de la configuration, validation des manifestes | |
| images (x4) | lint du Dockerfile, build, scan Trivy, push sur GHCR | le push ne se fait pas sur une pull request |
| deploy-dev | deploiement auto sur la branche `main` | voir "deploiements" ci-dessous |
| deploy-prod | deploiement sur un tag `vX.Y.Z`, validation manuelle, retour arriere auto si le test echoue | voir "deploiements" ci-dessous |

Ce qui peut encore poser probleme au premier vrai passage :

1. **Les audits de dependances** : `pip-audit` et `npm audit` n'ont jamais ete lances. Une CVE recente dans une
   dependance peut faire echouer le job. Il faudra alors mettre a jour la dependance ou ajouter une exception.
2. **Les jobs de deploiement** (ignores par defaut : ils ne se lancent que si la variable de depot `DEPLOY_ENABLED` vaut `true`, dans Settings, Secrets and variables, Actions, Variables) : ils ne peuvent pas atteindre le cluster local depuis les runners GitHub. Il faut
   soit un cluster accessible depuis Internet, soit un runner installe sur la machine. Il faut aussi creer dans
   GitHub ces secrets : `KUBECONFIG_DEV`, `KUBECONFIG_PROD`, `DEV_ADMIN_PASSWORD`, `PROD_ADMIN_PASSWORD`, et ces
   variables : `DEV_URL`, `PROD_URL`.
3. **La protection de la prod** : l'approbation manuelle demande de creer l'environnement `production` avec un
   relecteur dans les reglages GitHub (Settings, Environments).

Pour un rendu scolaire, les jobs qualite, scans et construction d'images sont ceux qui se montrent bien. Presenter
les deploiements comme ecrits mais non executes.

---

## Le dossier `scripts/` : a garder ?

Oui, de preference tout garder (quelques ko). Le rapport cite ces scripts par leur nom.

**Indispensables (lancement et deploiement) :**

| Script | A quoi il sert |
|---|---|
| `gen-env.sh` | cree le fichier `.env` avec les mots de passe. Sans lui, docker compose ne demarre pas |
| `deploy.sh` | deploie l'application sur Kubernetes (le pipeline CI l'appelle aussi) |
| `smoke_test.py` | test de bout en bout : compte, ticket, piece jointe, export CSV, mail (le pipeline l'appelle aussi) |
| `apply-monitoring.sh` | installe les regles d'alerte sur Kubernetes |

**Facultatifs, mais cites dans le rapport :**

| Script | A quoi il sert | Commande |
|---|---|---|
| `seed.py` | remplit l'appli avec des donnees de demo | voir l'option 1, etape 5 |
| `loadtest.py` | genere de la charge (autoscaling, resilience, mise a jour progressive) | `python scripts/loadtest.py --base-url https://helpdesk.localtest.me:8443 --insecure --email alice.martin@example.com --password "Demo-Helpdesk-2026" --duration 120 --concurrency 16` |
| `netpol-test.sh` | prouve que les politiques reseau sont appliquees | `bash scripts/netpol-test.sh helpdesk-prod` |
| `scan-images.sh` | scan de securite Trivy des 4 images | `bash scripts/scan-images.sh v1.1.0` |
| `canary-check.py` | mesure la repartition du trafic en canary | `python scripts/canary-check.py` |
| `finops-report.py` | chiffres FinOps (reserve et consomme, cout equivalent) | `python scripts/finops-report.py --namespace helpdesk-prod` |

Si tu en supprimes, rien ne casse a l'execution, mais le rapport et le jury les mentionnent : a eviter.

---

## Activer le deploiement dans GitHub (secrets et variables) : resume

A faire SEULEMENT si un cluster est joignable depuis Internet (ou avec un runner installe sur la machine).
Avec le cluster kind local, ne PAS creer `DEPLOY_ENABLED` : les deploiements restent ignores et le pipeline reste vert.

**1. Recuperer les valeurs (Git Bash)**

    # mots de passe admin
    kubectl -n helpdesk-dev  get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d; echo
    kubectl -n helpdesk-prod get secret helpdesk-secrets -o jsonpath='{.data.admin-password}' | base64 -d; echo

    # kubeconfig du compte ci-deployer (exemple dev ; pour la prod : NS=helpdesk-prod et kubeconfig-prod)
    NS=helpdesk-dev
    TOKEN=$(kubectl -n $NS create token ci-deployer --duration=720h)
    SERVER=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')
    CA=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
    cat > kubeconfig-dev <<EOF
    apiVersion: v1
    kind: Config
    clusters: [{name: c, cluster: {server: $SERVER, certificate-authority-data: $CA}}]
    users: [{name: ci, user: {token: $TOKEN}}]
    contexts: [{name: ctx, context: {cluster: c, user: ci, namespace: $NS}}]
    current-context: ctx
    EOF
    base64 -w0 kubeconfig-dev; echo

Le jeton dure 30 jours. Supprimer les fichiers `kubeconfig-*` apres usage (ils contiennent un jeton).

**2. Les creer dans GitHub** : Settings, Secrets and variables, Actions.

| Onglet | Nom | Valeur |
|---|---|---|
| Secrets | `DEV_ADMIN_PASSWORD` | mot de passe admin dev |
| Secrets | `PROD_ADMIN_PASSWORD` | mot de passe admin prod |
| Secrets | `KUBECONFIG_DEV` | la ligne base64 de dev |
| Secrets | `KUBECONFIG_PROD` | la ligne base64 de prod |
| Variables | `DEV_URL` | adresse de l'appli dev, avec `https://`, sans `/` final |
| Variables | `PROD_URL` | pareil pour la prod |
| Variables | `DEPLOY_ENABLED` | `true` (a creer en dernier) |

**3. Proteger la prod** : Settings, Environments, `production`, cocher "Required reviewers" et ajouter son compte.

**4. Protection de la branche main** (a faire dans tous les cas) : Settings, Branches, regle sur `main` : pull request
obligatoire, 1 approbation (ou aucune si on est seul), controles obligatoires (Back-end, Worker, Front-end, Detection de
secrets, Infrastructure), force push interdit. Settings, Code security : activer Dependabot alerts et security updates.

---

## Si ca ne marche pas

| Probleme | Solution |
|---|---|
| `Cannot connect to the Docker daemon` | Lancer Docker Desktop et attendre l'icone verte. |
| `docker compose` : commande inconnue | Ecrire `docker-compose` avec un tiret. |
| `variable is not set` | Le fichier `.env` manque : `bash scripts/gen-env.sh`. |
| Page vide juste apres le demarrage | Attendre 1 minute et recharger. |
| Erreur 429 apres plusieurs mauvais mots de passe | Attendre 5 minutes (protection anti force brute). |
| `localtest.me` introuvable | Pas d'Internet : voir le `README.md` (section Depannage). |

Pour plus de details (tests de charge, sauvegardes, Terraform, creation du cluster depuis zero) : `README.md`.
