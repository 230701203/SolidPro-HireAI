"""Hand-written content for MOCK mode. Every answer below was checked by a person (and the numeric ones by code).

Mock mode cannot write job-specific questions. It serves this small curated pool for common skills and marks every
other slot as a placeholder that cannot be approved until a reviewer rewrites it.
"""

# skill key -> list of (text, options, correct_index, explanation, difficulty, topic)
MCQ_POOL: dict[str, list[tuple[str, list[str], int, str, str, str]]] = {
    "python": [
        ("What does the expression `[x * 2 for x in range(3)]` evaluate to?", ["[0, 2, 4]", "[2, 4, 6]", "[0, 1, 2]", "[0, 2, 4, 6]"], 0, "range(3) yields 0, 1, 2 and each value is doubled.", "easy", "Core language"),
        ("Which of these Python types is immutable?", ["list", "dict", "tuple", "set"], 2, "Tuples cannot be changed after creation; lists, dicts and sets can.", "easy", "Data types"),
        ("What is the average time complexity of looking up a key in a Python dict?", ["O(1)", "O(n)", "O(log n)", "O(n log n)"], 0, "Dicts are hash tables, so lookups take constant time on average.", "medium", "Data structures"),
    ],
    "sql": [
        ("Which SQL clause filters rows after GROUP BY has been applied?", ["WHERE", "HAVING", "ORDER BY", "LIMIT"], 1, "HAVING filters groups; WHERE filters rows before grouping.", "easy", "Queries"),
        ("Which JOIN returns every row from the left table plus matching rows from the right table?", ["INNER JOIN", "RIGHT JOIN", "LEFT JOIN", "CROSS JOIN"], 2, "LEFT JOIN keeps all left rows and fills NULLs where the right side does not match.", "easy", "Joins"),
        ("What does COUNT(*) count?", ["Only non-NULL values of the first column", "All rows in the result, including rows containing NULLs", "Only distinct rows", "Only rows where every column is non-NULL"], 1, "COUNT(*) counts rows, regardless of NULLs.", "medium", "Aggregation"),
    ],
    "git": [
        ("Which command creates a new branch called `feature` and switches to it?", ["git checkout -b feature", "git branch -d feature", "git merge feature", "git stash feature"], 0, "`checkout -b` creates and switches in one step.", "easy", "Branching"),
        ("What does `git pull` do by default?", ["Uploads local commits to the remote", "Fetches from the remote and merges into the current branch", "Creates a new local repository", "Deletes the remote branch"], 1, "git pull is a fetch followed by a merge.", "easy", "Remotes"),
    ],
    "docker": [
        ("What is a Docker image?", ["A running container", "A read-only template used to create containers", "A virtual machine disk", "A network driver"], 1, "Containers are started from images.", "easy", "Concepts"),
        ("Which Dockerfile instruction sets the base image?", ["RUN", "CMD", "FROM", "COPY"], 2, "FROM must start a build stage and names the base image.", "easy", "Dockerfile"),
        ("Which command lists the running containers?", ["docker images", "docker ps", "docker build", "docker pull"], 1, "`docker ps` lists running containers.", "easy", "CLI"),
    ],
    "javascript": [
        ("What does the `===` operator do in JavaScript?", ["Assigns a value", "Compares value and type without coercion", "Compares only the value after coercion", "Compares object memory addresses only"], 1, "Strict equality does not convert types.", "easy", "Operators"),
        ("What does `typeof null` return?", ["\"null\"", "\"undefined\"", "\"object\"", "\"number\""], 2, "This is a long-standing quirk of the language.", "medium", "Core language"),
        ("Which array method adds an element to the end of an array?", ["pop", "shift", "unshift", "push"], 3, "push appends; pop removes the last element.", "easy", "Arrays"),
    ],
    "react": [
        ("Which hook manages local state in a function component?", ["useState", "useEffect", "useRef", "useContext"], 0, "useState returns the current value and a setter.", "easy", "Hooks"),
        ("Why should list items rendered with map() have a stable `key` prop?", ["It styles each item", "It lets React identify which items changed, were added or removed", "It makes items clickable", "It sorts the list"], 1, "Keys let React reconcile list updates efficiently and correctly.", "medium", "Rendering"),
    ],
    "rest": [
        ("Which HTTP status code means 'Not Found'?", ["200", "301", "404", "500"], 2, "404 means the server cannot find the requested resource.", "easy", "HTTP"),
        ("Which HTTP method is normally used to create a new resource in a REST API?", ["GET", "POST", "DELETE", "HEAD"], 1, "POST submits data to create a resource.", "easy", "REST"),
        ("Which HTTP method is idempotent and typically used to replace a resource completely?", ["POST", "PUT", "CONNECT", "TRACE"], 1, "Repeating the same PUT leaves the resource in the same state.", "medium", "REST"),
    ],
    "fastapi": [
        ("Which library does FastAPI use for request and response data validation?", ["Marshmallow", "Pydantic", "Cerberus", "Django forms"], 1, "FastAPI builds on Pydantic models.", "easy", "Framework"),
    ],
    "autocad": [
        ("In AutoCAD, which command draws a straight line segment?", ["CIRCLE", "ARC", "LINE", "ELLIPSE"], 2, "LINE draws straight segments between picked points.", "easy", "Drawing"),
        ("What does the TRIM command do in AutoCAD?", ["Copies objects", "Cuts objects at a cutting edge defined by other objects", "Rotates objects", "Scales objects"], 1, "TRIM removes the part of an object that crosses a cutting edge.", "medium", "Editing"),
    ],
}

ALIASES = {
    "postgresql": "sql", "postgres": "sql", "mysql": "sql", "sqlite": "sql", "t-sql": "sql", "pl/sql": "sql",
    "js": "javascript", "node": "javascript", "node.js": "javascript", "reactjs": "react", "react.js": "react",
    "rest api": "rest", "rest apis": "rest", "restful": "rest", "http": "rest", "api": "rest", "autocad 2d": "autocad",
    "github": "git", "python3": "python", "flask": "python", "django": "python",
}

SENTENCES: list[tuple[str, str]] = [
    ("Please review the project schedule before the meeting tomorrow morning.", "easy"),
    ("The engineering team completed the design review ahead of the deadline.", "easy"),
    ("We need to update the drawing and send it to the client by Friday.", "easy"),
    ("Accurate documentation helps new team members understand the system quickly.", "medium"),
    ("The software release was delayed because testing found several issues.", "medium"),
    ("Could you share the latest version of the report with the whole team?", "medium"),
    ("Regular communication between departments keeps every project on track.", "medium"),
    ("She explained the technical requirements clearly during the planning session.", "medium"),
    ("Our priority this quarter is to improve quality and reduce delivery time.", "medium"),
    ("The manager asked everyone to submit their weekly status updates on time.", "medium"),
    ("Careful measurement at the start prevents expensive mistakes later in production.", "hard"),
    ("Please confirm that the new configuration works correctly in the test environment.", "hard"),
]

# Starter aptitude questions: (topic, text, options, correct_index, explanation, difficulty)
APTITUDE_SEED: list[tuple[str, str, list[str], int, str, str]] = [
    ("numerical", "A train travels 180 km in 3 hours. At the same speed, how far does it travel in 5 hours?", ["270 km", "300 km", "330 km", "360 km"], 1, "Speed is 60 km/h, so 5 hours gives 300 km.", "easy"),
    ("numerical", "What is 15% of 240?", ["30", "36", "38", "40"], 1, "0.15 x 240 = 36.", "easy"),
    ("numerical", "The price of an item rises from 80 to 100. What is the percentage increase?", ["20%", "25%", "30%", "125%"], 1, "The increase is 20, and 20 / 80 = 25%.", "medium"),
    ("logical", "All engineers are problem solvers. Some problem solvers are artists. Which conclusion must be true?", ["All engineers are artists", "Some engineers are artists", "All artists are problem solvers", "None of the other statements must be true"], 3, "The premises do not link engineers and artists, so no other statement is guaranteed.", "medium"),
    ("logical", "All roses are flowers and all flowers need water. Which statement must be true?", ["All flowers are roses", "All roses need water", "Some water needs roses", "No roses need water"], 1, "Roses are flowers, and flowers need water, so roses need water.", "easy"),
    ("logical", "Asha is taller than Ravi. Ravi is taller than Meena. Who is the shortest?", ["Asha", "Ravi", "Meena", "Cannot be determined"], 2, "Asha > Ravi > Meena.", "easy"),
    ("analytical", "Task A takes 2 days. Tasks B (3 days) and C (4 days) both start after A finishes and run in parallel. What is the minimum total duration?", ["5 days", "6 days", "7 days", "9 days"], 1, "2 days for A, then the longer of B and C (4 days) = 6 days.", "medium"),
    ("analytical", "Three machines each make 20 parts per hour. How many hours do two machines need to make 120 parts?", ["2 hours", "3 hours", "4 hours", "6 hours"], 1, "Two machines make 40 parts per hour, so 120 parts take 3 hours.", "medium"),
    ("analytical", "A suite has 40 tests and 10% fail on the first run. After fixes, half of the failures pass. How many tests still fail?", ["2", "4", "5", "20"], 0, "10% of 40 is 4 failures; half of them (2) are fixed, so 2 still fail.", "easy"),
    ("verbal", "Choose the word closest in meaning to 'meticulous'.", ["Careless", "Careful and precise", "Quick", "Reluctant"], 1, "Meticulous means showing great attention to detail.", "easy"),
    ("verbal", "Choose the correct sentence.", ["The team have completed it's work.", "The team has completed its work.", "The team has completed it's work.", "The team have completed its' work."], 1, "'Team' is treated as singular here and 'its' is the possessive form.", "easy"),
    ("verbal", "Choose the word opposite in meaning to 'expand'.", ["Grow", "Contract", "Extend", "Increase"], 1, "To contract is to become smaller.", "easy"),
    ("data_interpretation", "Monthly sales were: January 120, February 150, March 90. What is the average monthly sales figure?", ["110", "120", "125", "130"], 1, "(120 + 150 + 90) / 3 = 120.", "easy"),
    ("data_interpretation", "Output fell from 500 units to 400 units. By what percentage did it fall?", ["10%", "20%", "25%", "80%"], 1, "The fall is 100 units, and 100 / 500 = 20%.", "medium"),
    ("data_interpretation", "A budget of 1,200 is split as Salaries 50%, Equipment 30% and Other for the rest. How much is Other?", ["120", "240", "360", "600"], 1, "Other is 20%, and 20% of 1,200 = 240.", "easy"),
    ("pattern", "What comes next in the series 2, 4, 8, 16, ?", ["24", "30", "32", "64"], 2, "Each term doubles.", "easy"),
    ("pattern", "What comes next in the series 1, 4, 9, 16, ?", ["20", "24", "25", "36"], 2, "These are the square numbers: 5 x 5 = 25.", "medium"),
    ("pattern", "What comes next in the series 2, 6, 12, 20, 30, ?", ["36", "40", "42", "44"], 2, "The differences are 4, 6, 8, 10, so the next difference is 12 and 30 + 12 = 42.", "hard"),
]
