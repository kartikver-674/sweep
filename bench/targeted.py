"""DQ2b: synthetic targeted-résumé families — one person, several positionings.

DQ1 (MULTI_TRACK_DERIVATION_QUALITY_AUDIT.md) found that targeted résumés of
one candidate derive nearly the same track, and DQ2a (track_intent.py) reads
the part of a résumé that says what it is aiming at. Neither can be measured
on bench/people.py: those are thirteen different people, whose facts already
differ. These are the missing fixtures.

Each FAMILY is one person. Every variant of a family shares, by construction:

  employers, held titles, locations and dates     FAMILIES[f]["jobs"]
  education                                        FAMILIES[f]["education"]
  the skill list — the SAME skills, every variant  FAMILIES[f]["skills"]
  a pool of true work bullets and true projects

and differs only in what a targeted résumé changes: the headline, the
summary, which true bullets and projects it chooses, how it describes them,
and how its skills are ordered or grouped. No variant states a fact another
contradicts — the challenge is shared facts plus different emphasis.

What each variant is FOR (its intended target and vocabulary) is NOT here.
It lives in bench/targeted_manifest.py, which nothing in this file, and
nothing in production, imports: the derivation sees only the document.

Layouts: `plain` and `twocol`, bench/render.py's CSS. Not `messy` — Chrome's
running header puts the absolute file:// path of the HTML into that PDF's
text, and these documents are committed and sent to a model.

    python -m bench.targeted --demo      # self-check, writes nothing
    python -m bench.targeted --build     # HTML + PDF into bench/resumes/targeted/
    python -m bench.targeted --capture   # the two local calls per document (Ollama)
"""

import contextlib
import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "auto-apply"))

from bench import render

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(HERE, "resumes", "targeted")
CAPTURES = os.path.join(HERE, "results", "targeted-qwen3_8b.json")
MODEL = "qwen3:8b"
LAYOUTS = ("plain", "twocol")
NOW = (2026, 9)          # "Present" is pinned, so a replay never drifts

# The Sweep preferences every derivation here uses: the app's India default
# (sweep/tests/test_one_track_goldens.prefs_for("india"), pinned by a test).
PREFS = {
    "locations": ["Delhi", "Gurgaon", "Bengaluru", "Hyderabad", "Pune", "Mumbai"],
    # None since 2026-11-20: make_profile.levels_for sets the cut from the
    # résumé's years.
    "exclude_levels": None,
    "avoid": [], "min_comp_usd": None, "max_spend_usd": None, "remote_scopes": [],
    "work_scope": "india",
    "location_hints": ["ahmedabad", "bangalore", "bengaluru", "bhubaneswar",
                       "bombay", "chandigarh", "chennai", "cochin", "coimbatore",
                       "delhi", "gurgaon", "gurugram", "hyderabad", "india",
                       "indore", "jaipur", "kochi", "kolkata", "lucknow", "mohali",
                       "mumbai", "mysore", "mysuru", "nagpur", "ncr", "noida",
                       "panchkula", "pune", "secunderabad", "thane",
                       "thiruvananthapuram", "trivandrum", "vadodara",
                       "visakhapatnam", "remote", "anywhere", "worldwide"],
    "max_age_days": None, "max_results": None,
    "linkedin_locations": ["Delhi", "Gurgaon", "Bengaluru", "Hyderabad", "Pune", "Mumbai"],
    "linkedin_remote_only": False, "sites_enabled": None,
    "allow_partial_paid_sweep": None,
}


# ===========================================================================
# The families. Names, employers and projects are invented; emails are
# example.com; phone numbers are in ranges reserved for fiction (Ofcom's
# 07700 900xxx, North America's 555-01xx).
# ===========================================================================

FAMILIES = {
    # ------------------------------------------------------------------ app
    "app": {
        "name": "Maya Lindqvist",
        "email": "maya.lindqvist@example.com",
        "phone": "+44 7700 900417",
        "location": "Manchester, UK",
        "skills": ["JavaScript", "TypeScript", "React", "Next.js", "Redux", "HTML",
                   "CSS", "Tailwind CSS", "React Native", "Expo", "iOS", "Android",
                   "Node.js", "Express", "GraphQL", "REST APIs", "PostgreSQL", "Jest",
                   "Cypress", "Git"],
        "jobs": [
            {"company": "Pebblestone Health", "title": "Senior Software Engineer",
             "location": "Manchester, UK", "start": "2023-09", "end": None,
             "bullets": {
                 "web": "Led the rebuild of the patient booking web app in React and "
                        "TypeScript on Next.js, cutting page load time by 38%.",
                 "mobile": "Built the React Native app for iOS and Android with Expo, "
                           "with offline appointment sync and push reminders; rated "
                           "4.7 on 30k installs.",
                 "api": "Designed the Node.js and GraphQL services behind both apps, "
                        "with PostgreSQL for booking data.",
                 "quality": "Set up Jest and Cypress test suites and an accessibility "
                            "review that brought the web app to WCAG 2.1 AA.",
                 "library": "Shipped a shared component library used by the web and "
                            "mobile teams.",
                 "crash": "Cut the mobile crash rate from 2.1% to 0.3% by profiling "
                          "React Native startup and native module usage.",
             }},
            {"company": "Northgate Commerce", "title": "Software Engineer",
             "location": "Manchester, UK", "start": "2021-06", "end": "2023-08",
             "bullets": {
                 "store": "Developed product listing and checkout pages in React and "
                          "Redux for a storefront with 200k monthly users.",
                 "orders": "Built REST APIs in Node.js and Express for the order service.",
                 "companion": "Maintained the React Native companion app and released "
                              "it to the App Store and Google Play.",
                 "e2e": "Wrote end-to-end tests in Cypress for the checkout flow.",
             }},
        ],
        "education": [
            {"institution": "University of Sheffield", "degree": "BSc Computer Science",
             "start": "2017-09", "end": "2020-07"},
        ],
        "projects": {
            "tidewell": {"name": "Tidewell", "stack": "React Native, Expo",
                         "blurb": "Built an offline-first habit tracker in React Native "
                                  "and Expo with background sync; published on iOS "
                                  "and Android."},
            "trailnote": {"name": "Trailnote", "stack": "React Native",
                          "blurb": "Developed a trail-mapping app in React Native with "
                                   "offline map tiles for iOS and Android."},
            "palette": {"name": "Palette Kit", "stack": "React, TypeScript",
                        "blurb": "Designed an accessible component library in React and "
                                 "TypeScript with visual regression tests in Cypress."},
            "shiftboard": {"name": "Shiftboard", "stack": "Next.js, Node.js, GraphQL, "
                                                          "PostgreSQL",
                           "blurb": "Built a shift-scheduling app end to end with "
                                    "Next.js, Node.js, GraphQL and PostgreSQL for a "
                                    "local clinic."},
        },
        "variants": {
            "frontend": {
                "headline": "Frontend Engineer",
                "summary": "Frontend engineer with five years of experience building fast, "
                           "accessible web applications in React, TypeScript and Next.js. "
                           "I care about performance budgets, design systems and WCAG "
                           "compliance, and I work closely with designers to ship "
                           "polished interfaces.",
                "bullets": [["web", "quality", "library", "api"],
                            ["store", "e2e", "orders"]],
                "projects": [("palette", None),
                             ("shiftboard", "Built the Next.js and React interface of a "
                                            "shift-scheduling app for a local clinic, "
                                            "with Tailwind CSS and a GraphQL client.")],
                "skills": {"groups": [
                    ("Frontend", ["React", "TypeScript", "JavaScript", "Next.js", "Redux",
                                  "HTML", "CSS", "Tailwind CSS"]),
                    ("Testing", ["Jest", "Cypress"]),
                    ("Backend", ["Node.js", "Express", "GraphQL", "REST APIs",
                                 "PostgreSQL"]),
                    ("Mobile", ["React Native", "Expo", "iOS", "Android"]),
                    ("Tools", ["Git"])]},
            },
            "mobile": {
                "headline": "Mobile Engineer",
                "summary": "Mobile engineer with five years of experience shipping React "
                           "Native apps to iOS and Android. Focused on offline-first "
                           "behaviour, app performance and smooth App Store and Google "
                           "Play releases.",
                "bullets": [["mobile", "crash", "library", "api"],
                            ["companion", "store", "orders"]],
                "projects": [("tidewell", None), ("trailnote", None)],
                "skills": {"groups": [
                    ("Mobile", ["React Native", "Expo", "iOS", "Android", "Redux"]),
                    ("Web", ["React", "Next.js", "TypeScript", "JavaScript", "HTML", "CSS",
                             "Tailwind CSS"]),
                    ("Backend", ["Node.js", "Express", "GraphQL", "REST APIs",
                                 "PostgreSQL"]),
                    ("Testing", ["Jest", "Cypress"]),
                    ("Tools", ["Git"])]},
            },
            "fullstack": {
                "headline": "Software Engineer",
                "summary": "Full-stack engineer who owns features end to end, from React "
                           "and Next.js interfaces to Node.js and GraphQL services and "
                           "PostgreSQL schemas. Comfortable on web and mobile clients "
                           "and on the APIs behind them.",
                "bullets": [["api", "web", "mobile", "quality"],
                            ["orders", "store", "companion"]],
                "projects": [("shiftboard", None), ("tidewell", None)],
                "skills": {"groups": [
                    ("Languages", ["TypeScript", "JavaScript"]),
                    ("Frontend", ["React", "Next.js", "Redux", "HTML", "CSS",
                                  "Tailwind CSS"]),
                    ("Backend", ["Node.js", "Express", "GraphQL", "REST APIs",
                                 "PostgreSQL"]),
                    ("Mobile", ["React Native", "Expo", "iOS", "Android"]),
                    ("Testing & Tools", ["Jest", "Cypress", "Git"])]},
            },
            # The mobile variant again, word for word, but with its skills as
            # one flat list IN THE SAME ORDER: grouping is the only difference.
            "mobile-flat": {"like": "mobile", "skills": "flat"},
        },
    },
    # ------------------------------------------------------------- platform
    "platform": {
        "name": "Rafael Moreau",
        "email": "rafael.moreau@example.com",
        "phone": "+1 416 555 0142",
        "location": "Toronto, Canada",
        "skills": ["Python", "Go", "FastAPI", "gRPC", "REST APIs", "PostgreSQL", "Redis",
                   "Kafka", "Docker", "Kubernetes", "Terraform", "AWS", "GitHub Actions",
                   "Prometheus", "Grafana", "Linux"],
        "jobs": [
            {"company": "Quillon Payments", "title": "Senior Software Engineer",
             "location": "Toronto, Canada", "start": "2022-02", "end": None,
             "bullets": {
                 "ledger": "Designed and built payment-ledger APIs in Python and FastAPI "
                           "on PostgreSQL, handling 3M transactions a day.",
                 "idp": "Built an internal developer platform on Kubernetes with "
                        "Terraform modules and GitHub Actions templates, cutting new "
                        "service setup from two weeks to one day.",
                 "eks": "Migrated 40 services from EC2 to Amazon EKS on AWS with zero "
                        "downtime.",
                 "slo": "Introduced Prometheus and Grafana dashboards and SLO alerting "
                        "for every payment service.",
                 "kafka": "Implemented Kafka event streams for settlement and "
                          "reconciliation.",
                 "grpc": "Wrote Go gRPC services for fraud scoring with p99 latency "
                         "under 40 ms.",
             }},
            {"company": "Larchmont Freight", "title": "Software Engineer",
             "location": "Toronto, Canada", "start": "2019-03", "end": "2022-01",
             "bullets": {
                 "tracking": "Developed shipment-tracking REST APIs in Python with "
                             "PostgreSQL and Redis caching.",
                 "docker": "Containerised the monolith with Docker and moved deployments "
                           "to a CI/CD pipeline.",
                 "iac": "Automated AWS infrastructure provisioning with Terraform.",
                 "queries": "Optimised slow PostgreSQL queries, cutting API response time "
                            "by 60%.",
             }},
        ],
        "education": [
            {"institution": "University of Waterloo", "degree": "BEng Software Engineering",
             "start": "2014-09", "end": "2018-06"},
        ],
        "projects": {
            "ledgerlite": {"name": "Ledgerlite", "stack": "Python, FastAPI, PostgreSQL",
                           "blurb": "Built an open-source double-entry ledger service in "
                                    "Python with FastAPI and PostgreSQL."},
            "throttle": {"name": "Throttle", "stack": "Go, Redis",
                         "blurb": "Implemented a Redis-backed rate limiter in Go with a "
                                  "gRPC API."},
            "kubeforge": {"name": "Kubeforge", "stack": "Go, Kubernetes",
                          "blurb": "Built a Kubernetes operator in Go that creates a "
                                   "preview environment for every pull request."},
            "tfmods": {"name": "Terraform Modules", "stack": "Terraform, AWS",
                       "blurb": "Maintained open-source Terraform modules for AWS "
                                "networking and EKS clusters, used by 12 teams."},
            "workflowlint": {"name": "Workflow Lint", "stack": "Python, GitHub Actions",
                             "blurb": "Wrote a Python linter for GitHub Actions workflows "
                                      "that flags insecure permissions."},
        },
        "variants": {
            "backend": {
                "headline": "Backend Engineer",
                "summary": "Backend engineer with seven years of experience designing APIs "
                           "and data models for payments and logistics. I build services "
                           "in Python and Go on PostgreSQL, Redis and Kafka, with a focus "
                           "on correctness and latency.",
                "bullets": [["ledger", "grpc", "kafka", "slo"],
                            ["tracking", "queries", "docker"]],
                "projects": [("ledgerlite", None), ("throttle", None)],
                "skills": {"flat": ["Python", "Go", "FastAPI", "gRPC", "REST APIs",
                                    "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes",
                                    "AWS", "Terraform", "GitHub Actions", "Prometheus",
                                    "Grafana", "Linux"]},
            },
            # Mis-headed: the headline still names the sibling target, and the
            # body — summary, bullets, projects — is platform engineering.
            "platform": {
                "headline": "Backend Engineer",
                "summary": "Platform engineer building the internal developer platform "
                           "that product teams ship on: Kubernetes, Terraform, GitHub "
                           "Actions templates and paved-road tooling, with observability "
                           "built in.",
                "bullets": [["idp", "eks", "slo", "grpc"],
                            ["docker", "iac", "tracking"]],
                "projects": [("kubeforge", None), ("tfmods", None)],
                "skills": {"flat": ["Kubernetes", "Terraform", "GitHub Actions", "Docker",
                                    "Go", "Python", "AWS", "Prometheus", "Grafana", "Linux",
                                    "gRPC", "FastAPI", "REST APIs", "PostgreSQL", "Redis",
                                    "Kafka"]},
            },
            "cloud": {
                "headline": "Cloud / DevOps Engineer",
                "summary": "Cloud and DevOps engineer automating AWS infrastructure with "
                           "Terraform, running Kubernetes in production and building "
                           "CI/CD pipelines with GitHub Actions.",
                "bullets": [["eks", "idp", "slo"],
                            ["iac", "docker", "tracking"]],
                "projects": [("tfmods", None), ("workflowlint", None)],
                "skills": {"flat": ["AWS", "Terraform", "Kubernetes", "Docker",
                                    "GitHub Actions", "Linux", "Prometheus", "Grafana",
                                    "Python", "Go", "PostgreSQL", "Redis", "Kafka",
                                    "FastAPI", "gRPC", "REST APIs"]},
            },
            # The no-intent control: a generic headline, no summary, no
            # projects, a neutral selection of bullets, a flat list.
            "generic": {
                "headline": "Software Engineer",
                "summary": None,
                "bullets": [["ledger", "idp", "slo"],
                            ["tracking", "docker"]],
                "projects": [],
                "skills": {"flat": ["AWS", "Docker", "FastAPI", "GitHub Actions", "Go",
                                    "Grafana", "gRPC", "Kafka", "Kubernetes", "Linux",
                                    "PostgreSQL", "Prometheus", "Python", "Redis",
                                    "REST APIs", "Terraform"]},
            },
        },
    },
    # ----------------------------------------------------------------- data
    "data": {
        "name": "Leila Haddad",
        "email": "leila.haddad@example.com",
        "phone": "+44 7700 900583",
        "location": "Leeds, UK",
        "skills": ["Python", "SQL", "pandas", "PySpark", "Apache Airflow", "dbt",
                   "Snowflake", "AWS", "Docker", "FastAPI", "scikit-learn", "PyTorch",
                   "MLflow", "LLMs", "RAG", "Hugging Face", "pgvector", "Tableau",
                   "Looker", "Git"],
        "jobs": [
            {"company": "Corvid Retail Group", "title": "Data Engineer",
             "location": "Leeds, UK", "start": "2022-04", "end": None,
             "bullets": {
                 "pipelines": "Built batch and streaming pipelines in Python and PySpark, "
                              "orchestrated with Apache Airflow, loading 2 TB a day into "
                              "Snowflake.",
                 "warehouse": "Modelled the sales and inventory warehouse in dbt, with "
                              "tested and documented models used by 60 analysts.",
                 "forecast": "Trained and deployed a demand-forecasting model with "
                             "scikit-learn and MLflow that cut stock-outs by 12%.",
                 "assistant": "Built a RAG product Q&A assistant using LLMs, Hugging Face "
                              "embeddings and pgvector, served through FastAPI.",
                 "quality": "Set up data quality checks and lineage for 300 dbt models.",
                 "looker": "Built Looker dashboards on the dbt semantic layer for the "
                           "merchandising teams.",
             }},
            {"company": "Harbourline Insurance", "title": "Data Analyst",
             "location": "Leeds, UK", "start": "2020-07", "end": "2022-03",
             "bullets": {
                 "fraud": "Wrote SQL and Python analyses of claims data to find fraud "
                          "patterns.",
                 "tableau": "Built Tableau dashboards for underwriting KPIs.",
                 "reporting": "Automated monthly reporting with Python and pandas, saving "
                              "30 hours a month.",
                 "severity": "Built a claims-severity model in scikit-learn.",
             }},
        ],
        "education": [
            {"institution": "University of Leeds", "degree": "MSc Data Science",
             "start": "2019-09", "end": "2020-06"},
            {"institution": "University of York", "degree": "BSc Mathematics",
             "start": "2016-09", "end": "2019-06"},
        ],
        "projects": {
            "tideline": {"name": "Tideline", "stack": "Airflow, dbt, Snowflake",
                         "blurb": "Built an Apache Airflow and dbt pipeline that loads "
                                  "public transport feeds into Snowflake every five "
                                  "minutes."},
            "compactor": {"name": "Parquet Compactor", "stack": "PySpark",
                          "blurb": "Wrote a PySpark job that compacts small Parquet files "
                                   "and cut query costs by a third."},
            "shelfsense": {"name": "Shelfsense", "stack": "PyTorch, FastAPI",
                           "blurb": "Trained a PyTorch image classifier that spots empty "
                                    "shelves and deployed it behind FastAPI."},
            "docent": {"name": "Docent", "stack": "LLMs, RAG, pgvector",
                       "blurb": "Built a RAG assistant over policy documents using Hugging "
                                "Face embeddings, pgvector and an open-weights LLM."},
            "metricgarden": {"name": "Metric Garden", "stack": "dbt, Looker",
                             "blurb": "Built a dbt metrics layer and Looker explores over a "
                                      "public retail dataset."},
            "housing": {"name": "Housing Atlas", "stack": "Tableau, SQL",
                        "blurb": "Designed a Tableau dashboard of UK housing data, with "
                                 "SQL models for price and rent trends."},
        },
        "variants": {
            # The headline shares the contact line: "Data Engineer · email · …".
            "dataeng": {
                "headline": "Data Engineer",
                "headline_inline": True,
                "summary": "Data engineer building reliable batch and streaming pipelines "
                           "with Python, PySpark, Apache Airflow, dbt and Snowflake on "
                           "AWS.",
                "bullets": [["pipelines", "warehouse", "quality", "forecast"],
                            ["reporting", "fraud"]],
                "projects": [("tideline", None), ("compactor", None)],
                "skills": {"groups": [
                    ("Data Engineering", ["Python", "SQL", "PySpark", "Apache Airflow",
                                          "dbt", "Snowflake"]),
                    ("Cloud", ["AWS", "Docker"]),
                    ("Machine Learning", ["scikit-learn", "PyTorch", "MLflow", "LLMs",
                                          "RAG", "Hugging Face", "pgvector"]),
                    ("Analytics", ["pandas", "Tableau", "Looker"]),
                    ("Tools", ["FastAPI", "Git"])]},
            },
            "ml": {
                "headline": "Machine Learning Engineer",
                "summary": "Machine learning engineer who takes models from notebook to "
                           "production: forecasting with scikit-learn and PyTorch, "
                           "experiment tracking in MLflow, and LLM applications built on "
                           "RAG, embeddings and pgvector.",
                "bullets": [["forecast", "assistant", "pipelines"],
                            ["severity", "reporting"]],
                "projects": [("shelfsense", None), ("docent", None)],
                "skills": {"groups": [
                    ("Machine Learning", ["PyTorch", "scikit-learn", "MLflow", "LLMs",
                                          "RAG", "Hugging Face", "pgvector"]),
                    ("Languages", ["Python", "SQL"]),
                    ("Data", ["pandas", "PySpark", "Apache Airflow", "dbt", "Snowflake"]),
                    ("Serving & Cloud", ["FastAPI", "Docker", "AWS"]),
                    ("Tools", ["Tableau", "Looker", "Git"])]},
            },
            # A headline with no job-title head at all; the summary declares.
            "analytics": {
                "headline": "Data Professional",
                "summary": "Analytics engineer turning raw data into trusted models and "
                           "dashboards with dbt, SQL, Snowflake and Looker, and working "
                           "with finance and merchandising teams on the metrics they "
                           "report.",
                "bullets": [["warehouse", "looker", "quality"],
                            ["tableau", "fraud", "reporting"]],
                "projects": [("metricgarden", None), ("housing", None)],
                "skills": {"groups": [
                    ("Analytics", ["SQL", "dbt", "Looker", "Tableau", "pandas"]),
                    ("Data Platform", ["Snowflake", "Apache Airflow", "PySpark", "AWS"]),
                    ("Languages", ["Python"]),
                    ("Machine Learning", ["scikit-learn", "PyTorch", "MLflow", "LLMs",
                                          "RAG", "Hugging Face", "pgvector"]),
                    ("Tools", ["FastAPI", "Docker", "Git"])]},
            },
            # A control that positions nothing — no headline, a summary with
            # no role and no technology, no projects — but whose skills are
            # GROUPED machine-learning first, exactly as the ml variant's.
            # Only the grouping can say where it is aimed.
            "grouped-control": {
                "headline": None,
                "summary": "Engineer with six years of experience in data-heavy teams, "
                           "from reporting to production systems.",
                "bullets": [["pipelines", "forecast", "warehouse"],
                            ["fraud", "reporting"]],
                "projects": [],
                "skills": {"like": "ml"},
            },
        },
    },
    # -------------------------------------------------------------- quality
    "quality": {
        "name": "Jonah Whitfield",
        "email": "jonah.whitfield@example.com",
        "phone": "+1 512 555 0187",
        "location": "Austin, TX, USA",
        "skills": ["Python", "Java", "Bash", "pytest", "Playwright", "Selenium",
                   "REST Assured", "Postman", "k6", "REST APIs", "Jenkins",
                   "GitHub Actions", "Docker", "Kubernetes", "Terraform", "Prometheus",
                   "Grafana", "PostgreSQL", "Linux"],
        "jobs": [
            {"company": "Meadowlark Health", "title": "Software Engineer",
             "location": "Austin, TX", "start": "2022-07", "end": None,
             "bullets": {
                 "framework": "Built a Playwright and pytest end-to-end test framework "
                              "covering 900 scenarios, run on every pull request in "
                              "GitHub Actions.",
                 "contracts": "Designed contract tests for 30 REST APIs with REST Assured "
                              "and Postman collections.",
                 "automation": "Built Python automation services on PostgreSQL that "
                               "reconcile claims data between systems.",
                 "load": "Ran load tests with k6 and fixed bottlenecks that cut p95 "
                         "latency by 45%.",
                 "oncall": "Introduced Prometheus alerting and Grafana dashboards, and led "
                           "the on-call rotation for the claims platform.",
                 "envs": "Containerised the test and staging environments with Docker and "
                         "Kubernetes, managed with Terraform.",
             }},
            {"company": "Cobaltline Software", "title": "QA Engineer",
             "location": "Austin, TX", "start": "2020-01", "end": "2022-06",
             "bullets": {
                 "selenium": "Automated regression suites in Java with Selenium.",
                 "jenkins": "Maintained the Jenkins pipelines that ran nightly test "
                            "suites.",
                 "bash": "Wrote Bash scripts to provision test data on Linux servers.",
                 "triage": "Reported and triaged 400 defects with product teams.",
             }},
        ],
        "education": [
            {"institution": "Texas State University", "degree": "BS Computer Science",
             "start": "2015-08", "end": "2019-12"},
        ],
        "projects": {
            "flakehound": {"name": "Flakehound", "stack": "Python, pytest",
                           "blurb": "Built a pytest plugin that detects and quarantines "
                                    "flaky tests."},
            "contractor": {"name": "Contractor", "stack": "Java, REST Assured",
                           "blurb": "Developed an API contract-testing CLI in Java with "
                                    "REST Assured."},
            "pagerlite": {"name": "Pagerlite", "stack": "Python, Prometheus, Grafana",
                          "blurb": "Built an incident-timeline bot in Python that turns "
                                   "Prometheus and Grafana alerts into a postmortem "
                                   "draft."},
            "gameday": {"name": "Game Day Kit", "stack": "Kubernetes, Terraform",
                        "blurb": "Created a chaos-testing kit for Kubernetes with "
                                 "Terraform-managed game-day environments."},
            "reconcile": {"name": "Reconcile", "stack": "Python, PostgreSQL",
                          "blurb": "Built a Python service that reconciles CSV exports "
                                   "against PostgreSQL and reports mismatches."},
            "cronwatch": {"name": "Cronwatch", "stack": "Python, Docker",
                          "blurb": "Wrote a Python job runner in Docker that retries "
                                   "failed jobs and reports every run."},
        },
        "variants": {
            "sdet": {
                "headline": "Test Automation Engineer (SDET)",
                "summary": "Test automation engineer building fast, reliable test "
                           "frameworks with Playwright, pytest, Selenium and REST Assured, "
                           "and wiring them into CI with GitHub Actions and Jenkins.",
                "bullets": [["framework", "contracts", "load", "envs"],
                            ["selenium", "jenkins", "triage"]],
                "projects": [("flakehound", None), ("contractor", None)],
                "skills": {"groups": [
                    ("Test Automation", ["Playwright", "Selenium", "pytest",
                                         "REST Assured", "Postman", "k6"]),
                    ("Languages", ["Python", "Java", "Bash"]),
                    ("CI/CD", ["GitHub Actions", "Jenkins"]),
                    ("Infrastructure", ["Docker", "Kubernetes", "Terraform", "Linux"]),
                    ("Monitoring", ["Prometheus", "Grafana"]),
                    ("APIs & Data", ["REST APIs", "PostgreSQL"])]},
            },
            # Mis-headed toward the SDET sibling; the body is reliability,
            # and the summary names no role at all.
            "reliability": {
                "headline": "QA Automation Engineer",
                "summary": "I keep production healthy: SLOs and alerting with Prometheus "
                           "and Grafana, incident response, capacity testing with k6, and "
                           "infrastructure as code with Terraform on Kubernetes.",
                "bullets": [["oncall", "envs", "load", "framework"],
                            ["jenkins", "bash"]],
                "projects": [("pagerlite", None), ("gameday", None)],
                "skills": {"groups": [
                    ("Reliability", ["Prometheus", "Grafana", "k6", "Kubernetes",
                                     "Terraform", "Docker"]),
                    ("CI/CD", ["GitHub Actions", "Jenkins"]),
                    ("Languages", ["Python", "Bash", "Java"]),
                    ("Testing", ["pytest", "Playwright", "Selenium", "REST Assured",
                                 "Postman"]),
                    ("Platforms", ["Linux", "PostgreSQL", "REST APIs"])]},
            },
            # A generic headline; the summary names the role in lower case
            # mid-sentence, which DQ2a's precision-first titles do not read.
            "automation": {
                "headline": "Software Engineer",
                "summary": "I am a backend automation engineer: I build Python services "
                           "and REST APIs on PostgreSQL that remove manual work, and I "
                           "test them thoroughly with pytest.",
                "bullets": [["automation", "contracts", "framework"],
                            ["bash", "selenium"]],
                "projects": [("reconcile", None), ("cronwatch", None)],
                "skills": {"groups": [
                    ("Backend & Automation", ["Python", "Java", "Bash", "PostgreSQL",
                                              "REST APIs"]),
                    ("Testing", ["pytest", "Playwright", "Selenium", "REST Assured",
                                 "Postman", "k6"]),
                    ("CI/CD", ["GitHub Actions", "Jenkins"]),
                    ("Infrastructure", ["Docker", "Kubernetes", "Terraform", "Linux"]),
                    ("Monitoring", ["Prometheus", "Grafana"])]},
            },
            "automation-flat": {"like": "automation", "skills": "flat"},
        },
    },
}


# ===========================================================================
# Variants and documents
# ===========================================================================

def variant(family, name):
    """One variant, resolved: a "like" variant is its original with only the
    named difference (skills flattened in the same order, or another
    variant's skills section borrowed)."""
    spec = FAMILIES[family]["variants"][name]
    if "like" in spec:
        base = copy.deepcopy(variant(family, spec["like"]))
        if spec.get("skills") == "flat":
            base["skills"] = {"flat": skill_order(base["skills"])}
        return base
    spec = copy.deepcopy(spec)
    if "like" in spec["skills"]:
        spec["skills"] = copy.deepcopy(variant(family, spec["skills"]["like"])["skills"])
    return spec


def skill_order(skills):
    """Every skill a skills section lists, in the order it lists them."""
    if "flat" in skills:
        return list(skills["flat"])
    return [s for _label, group in skills["groups"] for s in group]


def variant_ids():
    """["app-frontend", ...] in family order."""
    return [f"{f}-{v}" for f, fam in FAMILIES.items() for v in fam["variants"]]


def split(variant_id):
    family, _, name = variant_id.partition("-")
    return family, name


def documents():
    """(doc id, variant id, layout) for every document, in a fixed order."""
    return [(f"{vid}-{layout}", vid, layout)
            for vid in variant_ids() for layout in LAYOUTS]


def person(variant_id):
    """The variant as bench/render.py's helpers read a person."""
    family, name = split(variant_id)
    fam, spec = FAMILIES[family], variant(family, name)
    jobs = [dict(job, bullets=[job["bullets"][b] for b in chosen])
            for job, chosen in zip(fam["jobs"], spec["bullets"])]
    projects = []
    for pid, blurb in spec["projects"]:
        project = fam["projects"][pid]
        projects.append({"name": project["name"], "stack": [project["stack"]],
                         "blurb": blurb or project["blurb"]})
    return {"name": fam["name"], "email": fam["email"], "phone": fam["phone"],
            "location": fam["location"], "headline": spec["headline"],
            "headline_inline": spec.get("headline_inline", False),
            "summary": spec["summary"], "skills": spec["skills"],
            "employment": jobs, "education": fam["education"],
            "projects": projects, "certifications": []}


def facts(variant_id):
    """What every sibling must agree on — the person, not the positioning."""
    fam = FAMILIES[split(variant_id)[0]]
    return {"name": fam["name"], "email": fam["email"],
            "companies": sorted({j["company"] for j in fam["jobs"]}),
            "titles": [j["title"] for j in fam["jobs"]],
            "date_ranges": [(j["start"], j["end"]) for j in fam["jobs"]],
            "education": [(e["degree"], e["institution"]) for e in fam["education"]],
            "skills": sorted(fam["skills"])}


def _skills_html(skills):
    esc = render._esc
    if "flat" in skills:
        return f'<div class="row">{esc(", ".join(skills["flat"]))}</div>'
    return "".join(f'<div class="row">{esc(label)}: {esc(", ".join(group))}</div>'
                   for label, group in skills["groups"])


def to_html(variant_id, layout):
    """One variant, one layout — render.py's CSS and entry helpers, plus the
    two sections its people never have: a summary and grouped skills."""
    p, esc, section = person(variant_id), render._esc, render._section
    contact = [p["email"], p["phone"], p["location"]]
    if p["headline"] and p["headline_inline"]:
        contact.insert(0, p["headline"])
    head = (f'<h1>{esc(p["name"])}</h1>'
            f'<div class="contact">{esc(" · ".join(contact))}</div>'
            + (f'<div class="headline">{esc(p["headline"])}</div>'
               if p["headline"] and not p["headline_inline"] else ""))
    summary = section("Summary", f'<div class="row">{esc(p["summary"])}</div>'
                      if p["summary"] else "")
    skills = section("Skills", _skills_html(p["skills"]))
    education = section("Education", render._education(p))
    experience = section("Experience", render._jobs_plain(p))
    projects = section("Projects", render._projects(p))
    if layout == "twocol":
        body = (head + f'<div class="wrap"><div class="side">{skills}{education}</div>'
                f'<div class="main">{summary}{experience}{projects}</div></div>')
    else:
        body = head + summary + skills + experience + projects + education
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<title>{esc(p["name"])}</title><style>'
            f'@page {{ size: A4; margin: 16mm; }}{render.CSS[layout]}{FIT}'
            f'</style></head><body>{body}</body></html>')


# render.py's twocol grid is 34% + 66% plus an 18pt gap: wider than the page,
# so the main column's right edge is cut off in the PDF and words vanish from
# its text (hana-twocol loses words in 10 of 16 bullets). Fixed here, not in
# render.py, whose committed PDFs have captures made from them.
FIT = ".wrap { grid-template-columns: 34% minmax(0, 1fr); }"


def pdf_path(doc):
    return os.path.join(OUT, f"{doc}.pdf")


def build(out_dir=None):
    """Write every document's HTML and drive Chrome to PDF (as render.build)."""
    out_dir = out_dir or OUT
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for doc, vid, layout in documents():
        stem = os.path.join(out_dir, doc)
        with open(stem + ".html", "w", encoding="utf-8") as fh:
            fh.write(to_html(vid, layout))
        subprocess.run([render.CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
                        "--virtual-time-budget=3000", f"--print-to-pdf={stem}.pdf",
                        "--no-pdf-header-footer", "file://" + stem + ".html"],
                       capture_output=True, timeout=120)
        if os.path.exists(stem + ".pdf"):
            written.append(stem + ".pdf")
    return written


def text_of(doc):
    from resume_parser import extract_text
    return extract_text(pdf_path(doc))


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# Capture: the two production calls, local model, loopback only
# ===========================================================================

LOOPBACK = ("127.0.0.1", "::1", "localhost")


@contextlib.contextmanager
def loopback_only(log):
    """Every connection this process opens goes to a loopback address, or the
    call raises. Each attempt is appended to `log` as (host, port)."""
    real = socket.socket.connect

    def connect(sock, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        log.append((host, address[1] if isinstance(address, tuple) else None))
        if host not in LOOPBACK:
            raise RuntimeError(f"non-loopback connection refused: {host}")
        return real(sock, address)

    socket.socket.connect = connect
    try:
        yield
    finally:
        socket.socket.connect = real


def _ollama(path):
    import urllib.request
    import local_extract
    with urllib.request.urlopen(local_extract.host() + path, timeout=10) as fh:
        return json.loads(fh.read())


def capture(path=None, limit=None):
    """Both local calls for every document not yet captured, saved after each.

    The production functions (local_extract.extract / .employment) through the
    production backend, which must resolve to local-direct on loopback; no
    other backend or model is ever substituted. Returns (captures, calls,
    connections)."""
    import inference
    import local_extract

    path = path or CAPTURES
    if (os.environ.get(inference.BACKEND_ENV) or inference.DEFAULT_BACKEND) != "local-direct":
        raise SystemExit("capture needs the local-direct backend")
    if local_extract.model_name(None) != MODEL:
        raise SystemExit(f"capture needs {MODEL}, not {local_extract.model_name(None)}")
    host = local_extract.host()
    if not host.startswith(("http://127.0.0.1:", "http://localhost:", "http://[::1]:")):
        raise SystemExit(f"capture needs a loopback Ollama, not {host}")

    data = {"meta": {}, "docs": {}}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    calls, connections = 0, []
    with loopback_only(connections):
        tags = {m["name"]: m for m in _ollama("/api/tags")["models"]}
        if MODEL not in tags:
            raise SystemExit(f"{MODEL} is not installed in the local Ollama")
        data["meta"] = {
            "model": MODEL,
            "model_digest": tags[MODEL]["digest"],
            "quantization": tags[MODEL].get("details", {}).get("quantization_level"),
            "parameter_size": tags[MODEL].get("details", {}).get("parameter_size"),
            "ollama_version": _ollama("/api/version")["version"],
            "backend": "local-direct (Ollama over loopback)",
            "calls_per_document": 2,
            "calls": ["local_extract.extract (FIELDS_PROMPT)",
                      "local_extract.employment (EMPLOYMENT_PROMPT)"],
            "prompt_sha256": {"fields": sha256(local_extract.FIELDS_PROMPT),
                              "employment": sha256(local_extract.EMPLOYMENT_PROMPT)},
            "options": "temperature 0, think false (inference.py)",
            "format": "docs[doc].fields is bench/results/qwen3_8b.json's entry shape; "
                      "docs[doc].employment is dates-qwen3_8b.json's",
        }
        todo = [d for d, _v, _l in documents() if d not in data["docs"]]
        for doc in todo[:limit] if limit else todo:
            text = text_of(doc)
            parsed, took = local_extract.extract(MODEL, text)
            calls += 1
            started = time.time()
            rows = local_extract.employment(MODEL, text)
            calls += 1
            data["docs"][doc] = {"text_sha256": sha256(text),
                                 "fields": {"parsed": parsed, "seconds": round(took, 2)},
                                 "employment": rows,
                                 "employment_seconds": round(time.time() - started, 2)}
            print(f"  {doc:<34} {took:5.1f}s + {time.time() - started:5.1f}s  "
                  f"{len(rows.get('employment') or [])} rows", flush=True)
            data["docs"] = dict(sorted(data["docs"].items(),
                                       key=lambda kv: [d for d, *_ in documents()].index(kv[0])))
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
    return data, calls, connections


# ===========================================================================
# Replay: today's derivation from the captures, no model and no network
# ===========================================================================

def load_captures(path=None):
    with open(path or CAPTURES, encoding="utf-8") as fh:
        return json.load(fh)


@contextlib.contextmanager
def _answers(entry):
    """The two model calls answered from a capture, "Present" pinned to NOW."""
    import local_extract
    real = local_extract.extract, local_extract.employment, local_extract.today
    local_extract.extract = lambda *a, **k: (copy.deepcopy(entry["fields"]["parsed"]), 0.0)
    local_extract.employment = lambda *a, **k: copy.deepcopy(entry["employment"])
    local_extract.today = lambda: NOW
    try:
        yield
    finally:
        local_extract.extract, local_extract.employment, local_extract.today = real


def derive(doc, captures, output_dir):
    """(text, derived, merged gate) for one document, exactly as production
    derives it under v2 with the frozen corpora (`output_dir` must hold no
    corpus). The caller owns the environment: SWEEP_PROFILE_ENGINE_VERSION=v2
    and no other SWEEP_* flag, as on Render."""
    import make_profile
    entry = captures["docs"][doc]
    text = text_of(doc)
    if sha256(text) != entry["text_sha256"]:
        raise ValueError(f"{doc}: the PDF's text is not the text that was captured")
    with _answers(entry):
        derived = make_profile.generate_local(text, copy.deepcopy(PREFS),
                                              log=lambda *a, **k: None,
                                              output_dir=output_dir)
    hints, _excludes, _record = make_profile._title_gate(derived,
                                                         make_profile._load_config())
    return text, derived, hints


def demo():
    ids = variant_ids()
    assert len(ids) == len(set(ids)) == 16, ids
    for vid in ids:
        family, name = split(vid)
        fam, spec, p = FAMILIES[family], variant(family, name), person(vid)
        # The same skills in every variant — only order and grouping move.
        assert sorted(skill_order(spec["skills"])) == sorted(fam["skills"]), vid
        # Every bullet and project is one of the family's true ones.
        assert len(spec["bullets"]) == len(fam["jobs"]), vid
        for job, chosen in zip(fam["jobs"], spec["bullets"]):
            assert chosen and set(chosen) <= set(job["bullets"]), (vid, chosen)
        assert {pid for pid, _b in spec["projects"]} <= set(fam["projects"]), vid
        for layout in LAYOUTS:
            doc = to_html(vid, layout)
            for value in (fam["name"], fam["email"], fam["phone"],
                          *(j["company"] for j in fam["jobs"]),
                          *(j["title"] for j in fam["jobs"]),
                          *(e["degree"] for e in fam["education"])):
                assert render._esc(value) in doc, (vid, layout, value)
            assert (p["summary"] is None) == ("<h2>Summary</h2>" not in doc), vid
    flat = person("app-mobile-flat")
    assert flat["skills"] == {"flat": skill_order(person("app-mobile")["skills"])}
    assert dict(flat, skills=None) == dict(person("app-mobile"), skills=None)
    assert person("data-grouped-control")["skills"] == person("data-ml")["skills"]
    assert len(documents()) == 32
    print(f"targeted demo ok — {len(FAMILIES)} families, {len(ids)} variants, "
          f"{len(documents())} documents")


def main():
    if "--demo" in sys.argv:
        return demo()
    if "--build" in sys.argv:
        written = build()
        return print(f"wrote {len(written)} PDFs to {OUT}")
    if "--capture" in sys.argv:
        _data, calls, connections = capture()
        hosts = sorted({h for h, _p in connections})
        return print(f"{calls} model calls; {len(connections)} connections, hosts {hosts}")
    print(__doc__)


if __name__ == "__main__":
    main()
