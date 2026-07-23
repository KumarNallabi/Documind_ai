from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        import mongoengine

        if settings.MONGO_USE_MOCK:
            # Lets the app + tests run without a real MongoDB instance.
            mongoengine.connect(
                db=settings.MONGO_DB_NAME,
                mongo_client_class=__import__("mongomock").MongoClient,
                alias="default",
            )
        else:
            mongoengine.connect(
                db=settings.MONGO_DB_NAME,
                host=settings.MONGO_URI,
                alias="default",
            )
