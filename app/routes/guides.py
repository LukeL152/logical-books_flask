from flask import Blueprint, render_template
import markdown

guides_bp = Blueprint('guides', __name__)

@guides_bp.route('/user_guide')
def user_guide():
    with open('USER_GUIDE.md', 'r') as f:
        user_guide_content = markdown.markdown(f.read())
    
    with open('BOOKKEEPING_GUIDE.md', 'r') as f:
        bookkeeping_guide_content = markdown.markdown(f.read())

    with open('BUDGETING_GUIDE.md', 'r') as f:
        budgeting_guide_content = markdown.markdown(f.read())

    return render_template('user_guide.html', 
                           user_guide_content=user_guide_content,
                           bookkeeping_guide_content=bookkeeping_guide_content,
                           budgeting_guide_content=budgeting_guide_content)
