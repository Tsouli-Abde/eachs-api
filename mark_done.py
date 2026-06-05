import requests, json, os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

MOODLE_URL = os.environ.get('MOODLE_URL', 'http://localhost:8080')
MOODLE_TOKEN = os.environ.get('MOODLE_TOKEN')

r = requests.get(f'{MOODLE_URL}/webservice/rest/server.php', params={
    'wstoken': MOODLE_TOKEN,
    'wsfunction': 'core_course_get_courses',
    'moodlewsrestformat': 'json'
})

logs = []
for course in r.json():
    if course['id'] <= 1:
        continue
    r2 = requests.get(f'{MOODLE_URL}/webservice/rest/server.php', params={
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'mod_assign_get_assignments',
        'moodlewsrestformat': 'json',
        'courseids[0]': course['id']
    })
    for c in r2.json().get('courses', []):
        for a in c.get('assignments', []):
            r3 = requests.get(f'{MOODLE_URL}/webservice/rest/server.php', params={
                'wstoken': MOODLE_TOKEN,
                'wsfunction': 'mod_assign_get_submissions',
                'moodlewsrestformat': 'json',
                'assignmentids[0]': a['id']
            })
            for assign in r3.json().get('assignments', []):
                for s in assign.get('submissions', []):
                    if s.get('status') == 'submitted':
                        logs.append({
                            'log_id': f'skip-{a["id"]}-{s["userid"]}',
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                            'student_id': str(s['userid']),
                            'assignment_id': str(a['id']),
                            'task_type': 'short_answer',
                            'question': '',
                            'student_answer': '',
                            'student_answer_preview': '',
                            'prompt_version': 'skip',
                            'prompt_used': '',
                            'proposed_score': 0,
                            'max_score': 100,
                            'confidence': 'skip',
                            'feedback': 'Marque comme traite sans evaluation',
                            'requires_human_review': False,
                            'backend': 'skip',
                            'course_name': course.get('shortname', ''),
                            'assignment_name': a['name'],
                            'student_name': '',
                            'human_final_score': None,
                            'human_decision': None,
                            'human_comment': None,
                            'reviewed_at': None
                        })

with open('audit_log.json', 'w') as f:
    json.dump(logs, f, indent=2, ensure_ascii=False)
print(f'{len(logs)} soumissions marquees comme traitees')