#!/usr/bin/env python3
"""Setup database with Alembic migrations"""
import os
import sys
import subprocess
import time

def run_command(cmd, cwd=None):
    """Run shell command and print output"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(result.stdout)
    return True

def main():
    """Main setup function"""
    # Переходим в корень проекта
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    print("=== Setting up database for Weight Control System ===")
    
    # Проверяем Docker
    print("Checking PostgreSQL...")
    subprocess.run("docker-compose up -d postgres", shell=True)
    time.sleep(3)
    
    # Устанавливаем Alembic
    print("\nInstalling Alembic...")
    run_command("pip install alembic")
    
    # Инициализируем Alembic
    if not os.path.exists("alembic"):
        print("\nInitializing Alembic...")
        run_command("alembic init alembic")
    
    # Обновляем alembic.ini
    print("\nConfiguring alembic.ini...")
    with open("alembic.ini", "r") as f:
        content = f.read()
    
    if "sqlalchemy.url = postgresql://weight_user:weight_pass@localhost:5432/weight_control" not in content:
        import re
        content = re.sub(
            r'sqlalchemy\.url = .*',
            'sqlalchemy.url = postgresql://weight_user:weight_pass@localhost:5432/weight_control',
            content
        )
        with open("alembic.ini", "w") as f:
            f.write(content)
        print("✓ alembic.ini configured")
    
    # Создаем миграцию
    print("\nCreating migration...")
    run_command("alembic revision --autogenerate -m 'Initial migration'")
    
    # Применяем миграцию
    print("\nApplying migration...")
    run_command("alembic upgrade head")
    
    # Проверяем таблицы
    print("\nVerifying tables...")
    run_command('docker-compose exec -T postgres psql -U weight_user -d weight_control -c "\\dt"')
    
    print("\n=== Database setup complete! ===")

if __name__ == "__main__":
    main()