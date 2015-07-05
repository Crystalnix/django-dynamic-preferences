from .settings import preferences_settings
from .exceptions import CachedValueNotFound, DoesNotExist

class PreferencesManager(object):
    """Handle retrieving / caching of preferences"""
    def __init__(self, model, registry, **kwargs):

        self.model = model

        self.registry = registry
        self.queryset = self.model.objects.all()
        self.instance = kwargs.get('instance')
        if self.instance:
            self.queryset = self.queryset.filter(instance=self.instance)

    @property
    def cache(self):
        from django.core.cache import caches
        return caches['default']

    def __getitem__(self, key):
        return self.get(key)

    def get_cache_key(self, section, name):
        """Return the cache key corresponding to a given preference"""
        if not self.instance:
            return 'dynamic_preferences_{0}_{1}_{2}'.format(self.model.__name__, section, name)
        return 'dynamic_preferences_{0}_{1}_{2}_{3}'.format(self.model.__name__, section, name, self.instance.pk)

    def from_cache(self, section, name):
        """Return a preference raw_value from cache"""
        cached_value = self.cache.get(self.get_cache_key(section, name), CachedValueNotFound)

        if cached_value is CachedValueNotFound:
            raise CachedValueNotFound
        return self.registry.get(section=section, name=name).serializer.deserialize(cached_value)

    def to_cache(self, pref):
        """Update/create the cache value for the given preference model instance"""
        self.cache.set(self.get_cache_key(pref.section, pref.name), pref.raw_value, None)

    def get(self, key, model=False):
        """Return the value of a single preference using a dotted path key"""
        try:
            section, name = key.split(preferences_settings.SECTION_KEY_SEPARATOR)
        except ValueError:
            name = key
            section = None
        if model:
            return self.queryset.get(section=section, name=name)
        try:
            return self.from_cache(section, name)
        except CachedValueNotFound:
            pass

        try:
            pref = self.queryset.get(section=section, name=name)
        except self.model.DoesNotExist:
            pref_obj = self.registry.get(section=section, name=name)
            pref = self.model.objects.create(section=section, name=name, raw_value=pref_obj.default)
        self.to_cache(pref)
        return pref.value

    def all(self):
        """Return a dictionnary containing all preferences by section
        Loaded from cache or from db in case of cold cache
        """
        a = {}
        try:
            for preference in self.registry.preferences():
                section = a.setdefault(preference.section, {})
                section[preference.name] = self.from_cache(preference.section, preference.name)
        except CachedValueNotFound:
            return self.load_from_db()

        return a

    def load_from_db(self):
        """Return a dictionnary of preferences by section directly from DB"""
        a = {}
        db_prefs = self.queryset
        for p in db_prefs:
            self.to_cache(p)
            section = a.setdefault(p.section, {})
            section[p.name] = self.from_cache(p.section, p.name)
