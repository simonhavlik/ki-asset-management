import sys
sys.path.insert(0, '.')
from app import create_app
from app.utils.performance import PerformanceCalculator

app = create_app()
with app.app_context():
    calculator = PerformanceCalculator()
    stats = calculator.recalculate_all()
    print(stats)