import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from groq import Groq

load_dotenv()

app = Flask(__name__)

MODEL = "openai/gpt-oss-20b"
API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=API_KEY) if API_KEY else None


def parse_json_object(content: str) -> dict[str, object]:
    decoder = json.JSONDecoder()
    for start, character in enumerate(content):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise json.JSONDecodeError("No JSON object found in model response", content, 0)


SYSTEM_PROMPT = """
You are CareerPilot, an expert technology career mentor for college students.

Your job is to turn a student's current profile and target role into a practical,
realistic, India-friendly career action plan.

Be encouraging but honest. Never guarantee a job, salary, interview, or placement.
Focus on skills, projects, portfolio evidence, interview readiness, and a sensible
learning sequence.

Return ONLY valid JSON with exactly these keys:
{
  "headline": "short motivating headline",
  "summary": "2-3 sentence personalized assessment",
  "readiness_score": 0,
  "target_role": "role",
  "priority_skills": [
    {"skill": "skill name", "reason": "why it matters"}
  ],
  "roadmap": [
    {"phase": "Weeks 1-2", "title": "short title", "tasks": ["task 1", "task 2", "task 3"]}
  ],
  "projects": [
    {"name": "project name", "why": "why this project improves employability"}
  ],
  "interview_focus": ["topic 1", "topic 2", "topic 3"],
  "next_actions": ["action 1", "action 2", "action 3", "action 4"]
}

Rules:
- readiness_score must be an integer from 0 to 100.
- priority_skills should contain 4 items.
- roadmap should contain 3 phases.
- each phase should contain 3 tasks.
- projects should contain 3 items.
- interview_focus should contain 4 items.
- next_actions should contain 4 items.
- Make the answer specific to the student's degree, year, current skills, target role,
  and stated goal.
- Do not invent certifications, experience, internships, or achievements.
- Keep wording concise enough for a dashboard.
"""


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/career-plan")
def career_plan():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    degree = str(data.get("degree", "")).strip()
    year = str(data.get("year", "")).strip()
    skills = str(data.get("skills", "")).strip()
    target_role = str(data.get("target_role", "")).strip()
    goal = str(data.get("goal", "")).strip()

    if not all([name, degree, year, skills, target_role, goal]):
        return jsonify({"error": "Please complete all profile fields before generating your plan."}), 400

    if len(goal) > 1000 or len(skills) > 1000:
        return jsonify({"error": "Please keep your skills and goal under 1000 characters each."}), 400

    if client is None:
        return jsonify({"error": "GROQ_API_KEY is missing. Add it to your .env file and restart the app."}), 503

    user_prompt = f"""
Student profile:
Name: {name}
Degree: {degree}
Year: {year}
Current skills: {skills}
Target technology role: {target_role}
Career goal: {goal}

Create the student's personalized career plan now.
"""

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_completion_tokens=2200,
        )

        content = completion.choices[0].message.content or ""
        plan = parse_json_object(content)

        # Minimal shape validation so broken model output doesn't crash the UI.
        required = [
            "headline", "summary", "readiness_score", "target_role",
            "priority_skills", "roadmap", "projects",
            "interview_focus", "next_actions"
        ]
        if not all(key in plan for key in required):
            raise ValueError("AI returned an incomplete career plan.")

        return jsonify({"plan": plan})

    except json.JSONDecodeError:
        return jsonify({
            "error": "The AI returned an unexpected format. Please try generating the plan again."
        }), 502
    except Exception as exc:
        app.logger.exception("Groq request failed: %s", exc)
        return jsonify({
            "error": "The AI service could not complete the request. Please check your API key and try again."
        }), 502


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
