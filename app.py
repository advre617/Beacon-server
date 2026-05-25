from flask import Flask
from flask_cors import CORS
from config import Config
from extensions.mongodb import init_mongo
from routes import endpoints, status, incidents, auth, check, ping, proxy, sse, profile

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    CORS(app,
        origins=["http://localhost:5173"],
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
    )

    init_mongo(app)
    
    app.register_blueprint(endpoints.bp)
    app.register_blueprint(status.bp)
    app.register_blueprint(incidents.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(check.bp)
    app.register_blueprint(ping.bp)
    app.register_blueprint(proxy.bp)
    app.register_blueprint(sse.bp)    
    app.register_blueprint(profile.bp)

    from services.sheduler import start_scheduler
    start_scheduler()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000, use_reloader=False)