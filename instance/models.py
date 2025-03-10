from datetime import datetime
import pytz
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Camera(db.Model):
    """Camera source configuration"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.UTC))
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'active': self.active
        }

class Zone(db.Model):
    """Zone configuration model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    points = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.UTC))
    active = db.Column(db.Boolean, default=True) # To soft delete zones
    camera_id = db.Column(db.Integer, db.ForeignKey('camera.id'), nullable=False) # Camera source
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'points': self.points
        }

class ZoneCount(db.Model):
    """Zone count history model"""
    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('zone.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    entries = db.Column(db.Integer, default=0)
    exits = db.Column(db.Integer, default=0)
    current_count = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.Index('idx_zone_timestamp', 'zone_id', 'timestamp'),
    )

    @classmethod
    def get_counts(cls, zone_id, start_time=None, end_time=None):
        query = cls.query.filter(cls.zone_id == zone_id)
        
        if start_time:
            query = query.filter(cls.timestamp >= start_time)
        if end_time:
            query = query.filter(cls.timestamp <= end_time)
            
        return query.order_by(cls.timestamp.desc()).all()
    
    @staticmethod
    def get_last_counts():
        """Get the last count record for each zone"""
        return (db.session.query(ZoneCount)
                .distinct(ZoneCount.zone_id)
                .order_by(ZoneCount.zone_id, ZoneCount.timestamp.desc())
                .all())
    