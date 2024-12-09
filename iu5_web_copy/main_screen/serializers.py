from main_screen.models import Public_Service, Addresses, Readings, CustomUser
from rest_framework import serializers
from collections import OrderedDict
from django.contrib.auth.hashers import make_password

class Rent_ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Public_Service
        fields = ["pk", "title", "price", "description", "icon", "icon1", "status"]

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False  # Устанавливаем поле как необязательное
                new_fields[name] = field
            return new_fields
        
class getCargoSerializer(serializers.Serializer):
     ServiceList = Rent_ServiceSerializer(many=True)
     OrderId = serializers.IntegerField(required=False,allow_null=True)
     items_in_cart = serializers.IntegerField()


class Rent_OrderServiceSerializer(serializers.ModelSerializer):
    # service = Rent_ServiceSerializer(read_only=True)

    class Meta:
        model = Readings
        fields = ["order", "service", "last_reading", "current_reading"]

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False  # Устанавливаем поле как необязательное
                new_fields[name] = field
            return new_fields

class ResolveOrder(serializers.ModelSerializer):
    class Meta:
        model = Addresses
        fields = ['status']

class Rent_OrderSerializer(serializers.ModelSerializer):
    services = Rent_OrderServiceSerializer(source='readings_set', many=True, read_only=True)
    # client = serializers.SerializerMethodField()

    class Meta:
        model = Addresses
        fields = ["pk", "order_date", "address", "status", "total_amount", "formation_date", "completion_date", "moderator", "client", "services"]

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False  # Устанавливаем поле как необязательное
                new_fields[name] = field
            return new_fields
        
class Adding_to_shippingSerializer(serializers.ModelSerializer):
        class Meta:
            model = Rent_OrderSerializer
            fields = ["pk", "order_date", "address", "status", "total_amount", "formation_date", "completion_date", "moderator", "client", "services"]
            read_only_fields = ["pk", "order_date","status", "total_amount", "formation_date", "completion_date", "moderator", "client", "services"]
            extra_kwargs = {
            'organization': {'read_only': False}
        }


    # def get_client(self, obj):
    #     return obj.client.id
        
class Rent_ServicesForRequestedSerializer(serializers.ModelSerializer):
     class Meta:
          model = Public_Service
          fields = ['pk', 'title', 'price', 'icon']

class RelatedSerializer(serializers.ModelSerializer):
     service = Rent_ServicesForRequestedSerializer()
     class Meta:
          model = Readings
          fields = ["order", "service", "last_reading", "current_reading"]

class Rent_Order_with_info_Serializer(serializers.ModelSerializer):
        services = RelatedSerializer(source='readings_set', many=True)

        class Meta:
            model = Addresses
            fields = ["pk", "order_date", "address", "status", "total_amount", "formation_date", "completion_date", "moderator", "client", "services"]
            
        
class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(default=False, required=False)
    is_superuser = serializers.BooleanField(default=False, required=False)
    class Meta:
        model = CustomUser
        fields = ['email', 'password', 'is_staff', 'is_superuser']


class Rent_OrderrSerializer(serializers.ModelSerializer):

    class Meta:
        model = Addresses
        fields = ["pk", "order_date", "address", "status", "total_amount", "formation_date", "completion_date", "moderator", "client"]

        def get_fields(self):
            new_fields = OrderedDict()
            for name, field in super().get_fields().items():
                field.required = False  # Устанавливаем поле как необязательное
                new_fields[name] = field
            return new_fields