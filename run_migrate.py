from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.append('scripts')
import migrate_templates
migrate_templates.migrate_templates()
