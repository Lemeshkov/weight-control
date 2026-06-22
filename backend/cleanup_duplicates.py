# backend/cleanup_duplicates.py
from database import SessionLocal
import models
from sqlalchemy import func

def cleanup_duplicates():
    db = SessionLocal()
    try:
        print("🔍 Поиск дубликатов...")

        # Находим дубликаты по vehicle_id + entry_time (без учета uniserver_code)
        duplicates = db.query(
            models.Trip.vehicle_id,
            models.Trip.entry_time,
            func.count(models.Trip.id).label('count')
        ).group_by(
            models.Trip.vehicle_id,
            models.Trip.entry_time
        ).having(
            func.count(models.Trip.id) > 1
        ).all()

        if not duplicates:
            print("✅ Дубликатов не найдено")
            return

        print(f"⚠️ Найдено {len(duplicates)} групп дубликатов")
        total_deleted = 0

        for dup in duplicates:
            # Находим все дубликаты в группе
            trips = db.query(models.Trip).filter(
                models.Trip.vehicle_id == dup.vehicle_id,
                models.Trip.entry_time == dup.entry_time
            ).order_by(models.Trip.id).all()

            # Оставляем первый (самый старый), удаляем остальные
            keep = trips[0]
            to_delete = trips[1:]

            print(f"  Группа: vehicle_id={dup.vehicle_id}, time={dup.entry_time}")
            print(f"    Оставляем ID: {keep.id}")
            print(f"    Удаляем ID: {[t.id for t in to_delete]}")

            for trip in to_delete:
                # Удаляем связанные записи
                db.query(models.EntryMeasurement).filter(
                    models.EntryMeasurement.trip_id == trip.id
                ).delete()

                db.query(models.ExitMeasurement).filter(
                    models.ExitMeasurement.trip_id == trip.id
                ).delete()

                db.query(models.LidarMeasurement).filter(
                    models.LidarMeasurement.trip_id == trip.id
                ).delete()

                db.query(models.UniserverEvent).filter(
                    models.UniserverEvent.trip_id == trip.id
                ).delete()

                # Удаляем сам рейс
                db.delete(trip)
                total_deleted += 1

            db.commit()

        print(f"✅ Очистка завершена. Удалено {total_deleted} дубликатов.")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_duplicates()