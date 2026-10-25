# Web Application Exercise

A little exercise to build a web application following an agile development process. See the [instructions](instructions.md) for more detail.

## Product vision statement

An application in which users can list gift cards they are looking to sell/swap, and which matches users who are looking for each other's gift cards.

## User stories

https://github.com/software-students-fall2026/web-app-exercise-teamgiftcardswap/issues/

## Task Board and Issues
Our task board for the first sprint is linked [here](https://github.com/orgs/software-students-fall2026/projects/60/), and our task board for the second sprint is linked [here](https://github.com/orgs/software-students-fall2026/projects/75/).
Our issues (across both sprints) are linked [here](https://github.com/software-students-fall2026/web-app-exercise-teamgiftcardswap/issues). 

## Steps necessary to run the software

Requires Python 3 and Docker.

1. Clone and install:

   ```bash
   git clone https://github.com/benzaslavsky/web-app-exercise-giftcard.git
   cd web-app-exercise-giftcard
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Start MongoDB:

   ```bash
   docker run --name cardswap-mongo -d -p 27017:27017 -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=secret mongo:7.0
   ```

3. Create your `.env`: `cp env.example .env`

   - `MONGO_URI`: database address and login (already matches step 2)
   - `MONGO_DBNAME`: database name
   - `SECRET_KEY`: signs login cookies, so replace it with a random string from `python3 -c "import secrets; print(secrets.token_hex(32))"`

4. Run:

   ```bash
   flask --app app run --debug --port 5050
   ```

   Open http://127.0.0.1:5050.

