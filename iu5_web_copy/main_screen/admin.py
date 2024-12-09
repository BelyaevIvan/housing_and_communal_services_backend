from django.contrib import admin

# Register your models here.
from .models import Addresses, Readings, Public_Service
admin.site.register(Addresses)
admin.site.register(Readings)
admin.site.register(Public_Service)