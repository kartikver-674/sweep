"""DQ2b ground truth: what each bench/targeted.py variant is FOR. Test-only.

Evaluation only. Nothing in production may import this module, and neither
may bench/targeted.py, which renders and derives the documents: the model
and the derivation see the résumé and nothing else. A test pins both.

Per variant:

  family, variant     which document family and which positioning
  case                strong_headline | generic_headline | misheaded |
                      control | control_grouped
  target              the intended target, in words (None for a control)
  title_terms         phrases that name the target in a job title or a role
                      keyword; matched as whole words after norm()
  vocabulary          concept terms that belong to the target; matched
                      against intent concept ids and weighted skills
  declared            the title phrase(s) the résumé itself writes for its
                      target, if any (what a reader sees, not what DQ2a reads)
  misleading          a title the résumé writes that names ANOTHER target
  twin_of             the variant this one repeats with a flat skills list

JOBS is a small labelled set of synthetic postings per family, no real
company. `kind` is specific (one variant's own target: `primary`), adjacent
(`adjacent_to` two targets, primary to neither) or generic (anyone's). No
expected score is written anywhere: the scorer decides.
"""
import re


def norm(text):
    """Lower case, punctuation to spaces: "Node.js" -> "node js"."""
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", str(text or "").lower()).split())


def has_phrase(text, phrase):
    """Is `phrase` in `text` as whole words, after norm()?"""
    return f" {norm(phrase)} " in f" {norm(text)} "


FAMILIES = ("app", "platform", "data", "quality")

VARIANTS = {
    # --------------------------------------------------------------- app
    "app-frontend": {
        "family": "app", "variant": "frontend", "case": "strong_headline",
        "target": "frontend web engineering",
        "title_terms": ["frontend", "front end", "ui developer", "ui engineer",
                        "web developer", "react developer", "react engineer",
                        "react js developer", "reactjs developer"],
        "vocabulary": ["react", "next.js", "html", "css", "tailwind css", "redux",
                       "accessibility", "wcag"],
        "declared": ["frontend engineer"], "misleading": [], "twin_of": None},
    "app-mobile": {
        "family": "app", "variant": "mobile", "case": "strong_headline",
        "target": "mobile app engineering (React Native, iOS, Android)",
        "title_terms": ["mobile", "react native", "ios", "android", "app developer"],
        "vocabulary": ["react native", "expo", "ios", "android", "app store",
                       "google play"],
        "declared": ["mobile engineer"], "misleading": [], "twin_of": None},
    "app-fullstack": {
        "family": "app", "variant": "fullstack", "case": "generic_headline",
        "target": "full-stack web engineering",
        "title_terms": ["full stack", "fullstack", "mern", "mean stack"],
        "vocabulary": ["node.js", "express", "graphql", "postgresql", "rest apis",
                       "next.js"],
        "declared": ["full-stack engineer"], "misleading": [], "twin_of": None},
    "app-mobile-flat": {
        "family": "app", "variant": "mobile-flat", "case": "strong_headline",
        "target": "mobile app engineering (React Native, iOS, Android)",
        "title_terms": ["mobile", "react native", "ios", "android", "app developer"],
        "vocabulary": ["react native", "expo", "ios", "android", "app store",
                       "google play"],
        "declared": ["mobile engineer"], "misleading": [], "twin_of": "app-mobile"},
    # ---------------------------------------------------------- platform
    "platform-backend": {
        "family": "platform", "variant": "backend", "case": "strong_headline",
        "target": "backend API engineering",
        "title_terms": ["backend", "back end", "api developer", "api engineer",
                        "python developer", "golang", "go developer", "server side"],
        "vocabulary": ["fastapi", "grpc", "postgresql", "redis", "kafka", "rest apis",
                       "go"],
        "declared": ["backend engineer"], "misleading": [], "twin_of": None},
    "platform-platform": {
        "family": "platform", "variant": "platform", "case": "misheaded",
        "target": "platform engineering (internal developer platform)",
        "title_terms": ["platform", "developer platform", "kubernetes",
                        "infrastructure"],
        "vocabulary": ["kubernetes", "terraform", "github actions", "docker",
                       "developer platform"],
        "declared": ["platform engineer"], "misleading": ["backend engineer"],
        "twin_of": None},
    "platform-cloud": {
        "family": "platform", "variant": "cloud", "case": "strong_headline",
        "target": "cloud / DevOps engineering",
        "title_terms": ["cloud", "devops", "dev ops", "aws", "site reliability",
                        "sre", "infrastructure"],
        "vocabulary": ["aws", "terraform", "kubernetes", "github actions", "ci/cd",
                       "docker"],
        "declared": ["devops engineer"], "misleading": [], "twin_of": None},
    "platform-generic": {
        "family": "platform", "variant": "generic", "case": "control",
        "target": None, "title_terms": [], "vocabulary": [],
        "declared": [], "misleading": [], "twin_of": None},
    # -------------------------------------------------------------- data
    "data-dataeng": {
        "family": "data", "variant": "dataeng", "case": "strong_headline",
        "target": "data engineering (pipelines, warehouse)",
        "title_terms": ["data engineer", "data engineering", "etl", "big data",
                        "data pipeline", "spark", "pyspark"],
        "vocabulary": ["pyspark", "apache airflow", "airflow", "dbt", "snowflake",
                       "etl"],
        "declared": ["data engineer"], "misleading": [], "twin_of": None},
    "data-ml": {
        "family": "data", "variant": "ml", "case": "strong_headline",
        "target": "machine learning / LLM engineering",
        "title_terms": ["machine learning", "ml engineer", "mlops", "ml ops",
                        "ai engineer", "llm", "gen ai", "genai", "generative ai",
                        "deep learning", "nlp", "applied scientist"],
        "vocabulary": ["pytorch", "scikit-learn", "mlflow", "llms", "llm", "rag",
                       "hugging face", "pgvector", "machine learning"],
        "declared": ["machine learning engineer"], "misleading": [], "twin_of": None},
    "data-analytics": {
        "family": "data", "variant": "analytics", "case": "generic_headline",
        "target": "analytics engineering / BI",
        "title_terms": ["analytics", "bi developer", "business intelligence",
                        "data analyst", "looker", "tableau"],
        "vocabulary": ["dbt", "looker", "tableau", "sql", "snowflake"],
        "declared": ["analytics engineer"], "misleading": [], "twin_of": None},
    "data-grouped-control": {
        "family": "data", "variant": "grouped-control", "case": "control_grouped",
        # Positions nothing in its header, summary or projects; its skills
        # section is data-ml's, grouped machine-learning first.
        "target": "machine learning / LLM engineering (grouping only)",
        "title_terms": ["machine learning", "ml engineer", "mlops", "ml ops",
                        "ai engineer", "llm", "gen ai", "genai", "generative ai",
                        "deep learning", "nlp", "applied scientist"],
        "vocabulary": ["pytorch", "scikit-learn", "mlflow", "llms", "llm", "rag",
                       "hugging face", "pgvector", "machine learning"],
        "declared": [], "misleading": [], "twin_of": None},
    # ----------------------------------------------------------- quality
    "quality-sdet": {
        "family": "quality", "variant": "sdet", "case": "strong_headline",
        "target": "test automation / SDET",
        "title_terms": ["sdet", "test automation", "automation test", "qa automation",
                        "quality assurance", "qa engineer", "test engineer",
                        "engineer in test"],
        "vocabulary": ["playwright", "selenium", "pytest", "rest assured", "postman",
                       "test automation"],
        "declared": ["test automation engineer"], "misleading": [], "twin_of": None},
    "quality-reliability": {
        "family": "quality", "variant": "reliability", "case": "misheaded",
        "target": "site reliability / DevOps",
        "title_terms": ["site reliability", "sre", "reliability", "devops",
                        "production engineer", "observability"],
        "vocabulary": ["prometheus", "grafana", "k6", "kubernetes", "terraform", "slo",
                       "incident response"],
        "declared": [], "misleading": ["qa automation engineer"], "twin_of": None},
    "quality-automation": {
        "family": "quality", "variant": "automation", "case": "generic_headline",
        "target": "backend automation engineering",
        "title_terms": ["backend", "back end", "python developer", "python engineer",
                        "automation developer"],
        "vocabulary": ["python", "postgresql", "rest apis"],
        "declared": ["backend automation engineer"], "misleading": [],
        "twin_of": None},
    "quality-automation-flat": {
        "family": "quality", "variant": "automation-flat", "case": "generic_headline",
        "target": "backend automation engineering",
        "title_terms": ["backend", "back end", "python developer", "python engineer",
                        "automation developer"],
        "vocabulary": ["python", "postgresql", "rest apis"],
        "declared": ["backend automation engineer"], "misleading": [],
        "twin_of": "quality-automation"},
}

# The three target variants of each family: the tracks one person would
# upload. Controls and flat twins are separate experiments.
SIBLINGS = {
    "app": ["app-frontend", "app-mobile", "app-fullstack"],
    "platform": ["platform-backend", "platform-platform", "platform-cloud"],
    "data": ["data-dataeng", "data-ml", "data-analytics"],
    "quality": ["quality-sdet", "quality-reliability", "quality-automation"],
}

HERE_IN_INDIA = "Bengaluru, Karnataka, India"


def _job(jid, family, kind, title, description, primary=None, adjacent_to=()):
    return {"id": jid, "family": family, "kind": kind, "primary": primary,
            "adjacent_to": list(adjacent_to), "Title": title,
            "Company": f"Synthetic Co {jid.upper()}", "Location": HERE_IN_INDIA,
            "Description": description}


JOBS = [
    # --------------------------------------------------------------- app
    _job("app01", "app", "specific", "React Native Engineer",
         "Build and ship our React Native app for iOS and Android. You will own offline "
         "sync, push notifications, app performance and App Store and Google Play "
         "releases. We use Expo, TypeScript and Redux.", primary="app-mobile"),
    _job("app02", "app", "specific", "Mobile Developer (iOS/Android)",
         "Develop cross-platform mobile features in React Native, integrate native "
         "modules for iOS and Android, profile startup time and crash rates, and publish "
         "releases through the App Store and Google Play.", primary="app-mobile"),
    _job("app03", "app", "specific", "Frontend Engineer",
         "Build fast, accessible web interfaces with React, TypeScript and Next.js. Own "
         "our design system and component library, performance budgets and WCAG "
         "accessibility, working closely with designers. HTML, CSS, Tailwind CSS and "
         "Jest.", primary="app-frontend"),
    _job("app04", "app", "specific", "UI Developer - React",
         "Craft accessible user interfaces in React and TypeScript with CSS and Tailwind "
         "CSS, build reusable components, write Cypress end-to-end tests and improve "
         "Core Web Vitals.", primary="app-frontend"),
    _job("app05", "app", "specific", "Full Stack Engineer",
         "Own features end to end: React and Next.js on the front end, Node.js, Express "
         "and GraphQL services on the back end, and PostgreSQL schemas and migrations.",
         primary="app-fullstack"),
    _job("app06", "app", "specific", "Full-Stack Developer (Node.js/React)",
         "Design REST APIs and GraphQL resolvers in Node.js and Express, model data in "
         "PostgreSQL, and build the React screens that use them. Jest tests across the "
         "stack.", primary="app-fullstack"),
    _job("app07", "app", "generic", "Software Engineer",
         "Join a product team building web and mobile applications. Write clean, tested "
         "code in TypeScript and JavaScript, review pull requests and collaborate with "
         "product and design. Git and agile experience."),
    _job("app08", "app", "generic", "Software Developer",
         "Develop and maintain features across our applications, write unit tests, fix "
         "bugs and take part in code reviews. JavaScript experience is a plus."),
    _job("app09", "app", "adjacent", "React Developer",
         "Build React web applications and contribute to our React Native mobile app. "
         "Redux, TypeScript, REST APIs and Jest.",
         adjacent_to=("app-frontend", "app-mobile")),
    _job("app10", "app", "adjacent", "JavaScript Engineer",
         "Work across Next.js front ends and Node.js back-end services, with TypeScript, "
         "GraphQL and PostgreSQL.", adjacent_to=("app-frontend", "app-fullstack")),
    # ---------------------------------------------------------- platform
    _job("plt01", "platform", "specific", "Backend Engineer (Python)",
         "Design and build APIs in Python and FastAPI on PostgreSQL and Redis. Model data, "
         "tune queries and own service latency and correctness. Kafka event streaming "
         "experience is a plus.", primary="platform-backend"),
    _job("plt02", "platform", "specific", "Golang Backend Developer",
         "Write Go services with gRPC and REST APIs, backed by PostgreSQL and Kafka, for a "
         "high-volume payments platform.", primary="platform-backend"),
    _job("plt03", "platform", "specific", "Platform Engineer",
         "Build our internal developer platform on Kubernetes: service templates, "
         "Terraform modules, GitHub Actions pipelines and self-service tooling for "
         "product teams. Go and Python.", primary="platform-platform"),
    _job("plt04", "platform", "specific", "Developer Platform Engineer",
         "Own the Kubernetes platform that product teams deploy to. Build operators in "
         "Go, preview environments and golden-path templates, and improve developer "
         "experience and deployment speed.", primary="platform-platform"),
    _job("plt05", "platform", "specific", "DevOps Engineer",
         "Automate AWS infrastructure with Terraform, maintain CI/CD pipelines in GitHub "
         "Actions, and run Docker workloads on Amazon EKS. Linux administration and "
         "monitoring with Prometheus and Grafana.", primary="platform-cloud"),
    _job("plt06", "platform", "specific", "Cloud Engineer (AWS)",
         "Design AWS networking, IAM and EKS clusters with Terraform, migrate workloads "
         "from EC2, manage cost and security, and build CI/CD with GitHub Actions.",
         primary="platform-cloud"),
    _job("plt07", "platform", "generic", "Software Engineer",
         "Build and operate services for our fintech platform. Python or Go, SQL, Docker "
         "and cloud experience. Take part in on-call and code reviews."),
    _job("plt08", "platform", "generic", "Software Development Engineer",
         "Write, test and deploy software for distributed systems. Linux, Git and one of "
         "Python, Java or Go."),
    _job("plt09", "platform", "adjacent", "Site Reliability Engineer",
         "Own SLOs, alerting with Prometheus and Grafana, incident response and capacity "
         "planning for Kubernetes services on AWS.",
         adjacent_to=("platform-platform", "platform-cloud")),
    _job("plt10", "platform", "adjacent", "Data Platform Engineer",
         "Operate Kafka, PostgreSQL and Redis clusters on Kubernetes, automated with "
         "Terraform.", adjacent_to=("platform-backend", "platform-platform")),
    # -------------------------------------------------------------- data
    _job("dat01", "data", "specific", "Data Engineer",
         "Build batch and streaming pipelines in Python and PySpark, orchestrate them "
         "with Apache Airflow, and model the warehouse in dbt on Snowflake. AWS, SQL and "
         "data quality testing.", primary="data-dataeng"),
    _job("dat02", "data", "specific", "ETL Developer - Spark",
         "Develop ETL jobs in PySpark and SQL, schedule them in Airflow, and optimise "
         "Parquet storage and warehouse loads.", primary="data-dataeng"),
    _job("dat03", "data", "specific", "Machine Learning Engineer",
         "Train, evaluate and deploy models with PyTorch and scikit-learn, track "
         "experiments in MLflow, and serve models behind FastAPI on Docker and AWS.",
         primary="data-ml"),
    _job("dat04", "data", "specific", "LLM Engineer (RAG)",
         "Build LLM applications with RAG: embeddings from Hugging Face models, vector "
         "search with pgvector, evaluation and prompt design. Python and FastAPI.",
         primary="data-ml"),
    _job("dat05", "data", "specific", "Analytics Engineer",
         "Own our dbt models and semantic layer on Snowflake, build Looker explores and "
         "dashboards, and define trusted metrics with finance and commercial teams. "
         "Strong SQL.", primary="data-analytics"),
    _job("dat06", "data", "specific", "BI Developer (Tableau/Looker)",
         "Design Tableau and Looker dashboards, write SQL models, and support business "
         "stakeholders with reporting and KPI definitions.", primary="data-analytics"),
    _job("dat07", "data", "generic", "Software Engineer",
         "Build internal tools and services in Python. SQL, Git, Docker and a willingness "
         "to learn across the stack."),
    _job("dat08", "data", "generic", "Technology Analyst",
         "Support data and software projects, write Python scripts and SQL queries, and "
         "document processes."),
    _job("dat09", "data", "adjacent", "Data Scientist",
         "Analyse retail data with Python, pandas and SQL, build forecasting models in "
         "scikit-learn, and present findings in Tableau.",
         adjacent_to=("data-ml", "data-analytics")),
    _job("dat10", "data", "adjacent", "MLOps Engineer",
         "Build pipelines that train and deploy models with Airflow, MLflow, Docker and "
         "AWS, with PySpark feature jobs.", adjacent_to=("data-ml", "data-dataeng")),
    # ----------------------------------------------------------- quality
    _job("qa01", "quality", "specific", "SDET",
         "Build and maintain automated test frameworks with Playwright, Selenium and "
         "pytest, write API tests with REST Assured and Postman, and run suites in "
         "GitHub Actions and Jenkins.", primary="quality-sdet"),
    _job("qa02", "quality", "specific", "QA Automation Engineer",
         "Automate regression, end-to-end and API tests for web applications with Java or "
         "Python and Selenium or Playwright. Own test strategy and defect triage.",
         primary="quality-sdet"),
    _job("qa03", "quality", "specific", "Site Reliability Engineer",
         "Own SLOs and alerting with Prometheus and Grafana, lead incident response and "
         "postmortems, run load tests with k6, and manage Kubernetes with Terraform.",
         primary="quality-reliability"),
    _job("qa04", "quality", "specific", "DevOps / SRE Engineer",
         "Keep production healthy: observability, on-call, infrastructure as code with "
         "Terraform, Kubernetes and Docker, and CI/CD with GitHub Actions.",
         primary="quality-reliability"),
    _job("qa05", "quality", "specific", "Backend Engineer (Python)",
         "Build Python services and REST APIs on PostgreSQL that automate business "
         "workflows, write pytest suites, and containerise them with Docker.",
         primary="quality-automation"),
    _job("qa06", "quality", "specific", "Python Automation Developer",
         "Automate data reconciliation and back-office processes with Python, PostgreSQL "
         "and REST APIs; schedule jobs and build reports.",
         primary="quality-automation"),
    _job("qa07", "quality", "generic", "Software Engineer",
         "Develop and test software for our healthcare platform. Python or Java, Git, "
         "Linux and agile teamwork."),
    _job("qa08", "quality", "generic", "Software Engineer II",
         "Design, build and test features, take part in code reviews, and work with "
         "Docker and CI pipelines."),
    _job("qa09", "quality", "adjacent", "Performance Test Engineer",
         "Design load tests with k6 and JMeter, analyse latency, and work with SREs on "
         "capacity.", adjacent_to=("quality-sdet", "quality-reliability")),
    _job("qa10", "quality", "adjacent", "Build and Release Engineer",
         "Maintain Jenkins and GitHub Actions pipelines, Docker images and Bash tooling on "
         "Linux.", adjacent_to=("quality-reliability", "quality-automation")),
]


def demo():
    assert set(VARIANTS) == {f"{v['family']}-{v['variant']}" for v in VARIANTS.values()}
    for family, sibs in SIBLINGS.items():
        assert len(sibs) == 3 and all(VARIANTS[s]["family"] == family for s in sibs)
        assert all(VARIANTS[s]["case"] not in ("control", "control_grouped") for s in sibs)
    ids = [j["id"] for j in JOBS]
    assert len(ids) == len(set(ids))
    for job in JOBS:
        if job["kind"] == "specific":
            assert job["primary"] in SIBLINGS[job["family"]], job["id"]
        else:
            assert job["primary"] is None, job["id"]
        assert set(job["adjacent_to"]) <= set(SIBLINGS[job["family"]]), job["id"]
    assert has_phrase("React Native Engineer", "react native")
    assert not has_phrase("React Native Engineer", "react developer")
    assert has_phrase("Node.js developer", "node.js")
    print(f"manifest demo ok — {len(VARIANTS)} variants, {len(JOBS)} jobs")


if __name__ == "__main__":
    demo()
