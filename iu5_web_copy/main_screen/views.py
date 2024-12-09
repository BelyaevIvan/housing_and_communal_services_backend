from rest_framework import viewsets, status
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.http import HttpResponse
from minio import Minio
from rest_framework.views import APIView
from django.conf import settings
from .models import Public_Service, Addresses, Readings, CustomUser
from .serializers import ResolveOrder, Rent_ServicesForRequestedSerializer, RelatedSerializer, Rent_Order_with_info_Serializer, Rent_ServiceSerializer, Rent_OrderSerializer, Rent_OrderServiceSerializer, UserSerializer, Rent_OrderrSerializer
# from .permissions import IsAdmin, IsManager
from datetime import datetime, timedelta, timezone
from .minio import add_pic  # Импортируем функцию для работы с MinIO
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes, parser_classes
from drf_yasg.utils import swagger_auto_schema
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from .permissions import IsAuth,IsAdmin,IsAuthManager,IsManager
from .auth import Auth_by_Session,AuthIfPos
from .redis import session_storage
from django.db.models import Q, F
import uuid
from rest_framework.parsers import FormParser,MultiPartParser
from drf_yasg import openapi
import os.path


@swagger_auto_schema(method='post',
                     request_body=UserSerializer,
                     responses={
                         status.HTTP_201_CREATED: "Created",
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                     })
@api_view(['POST'])
@permission_classes([AllowAny])
def create_user(request):
    serializer = UserSerializer(data=request.data)
    
    # Убираем проверку на валидность, просто создаем пользователя
    if serializer.is_valid(raise_exception=False):  # Установите raise_exception в False, чтобы избежать исключений
        user = serializer.create(serializer.validated_data)
        return Response({"message": "Пользователь создан", "user_id": user.id}, status=201)
    
    # Если нужно, можно добавить обработку ошибок
    return Response({"error": "Ошибка создания пользователя"}, status=400)


@csrf_exempt
@swagger_auto_schema(method='post', request_body=UserSerializer)
@api_view(['Post'])
@permission_classes([AllowAny])
@parser_classes((FormParser,))
def login_view(request):
    email = request.POST.get('email')
    password = request.POST.get('password')
    # user = authenticate(email=email, password=password)
    user = CustomUser.objects.filter(email=email, password=password).first()
    print(email,password)
    if user is not None:
        session_id = str(uuid.uuid4())
        session_storage.set(session_id, email)
        response = Response(status=status.HTTP_201_CREATED)
        response.set_cookie("session_id", session_id, samesite="lax")
        return response
    return Response({'error': 'Invalid Credentials'}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(method='post',
                     responses={
                         status.HTTP_204_NO_CONTENT: "No content",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                     })

@api_view(['Post'])
@permission_classes([IsAuth])

def logout_view(request):
    session_id = request.COOKIES["session_id"]
    print(session_id)
    if session_storage.exists(session_id):
        print('1')
        session_storage.delete(session_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    return Response(status=status.HTTP_403_FORBIDDEN)


@swagger_auto_schema(
    method='put',
    request_body=UserSerializer,
    responses={
        status.HTTP_200_OK: "Password updated successfully",
        status.HTTP_400_BAD_REQUEST: "Bad Request - Invalid data or user not found",
    }
)
@api_view(['PUT'])
@permission_classes([IsAuth])
def update_password(request):
    # Извлекаем email и новый пароль из запроса
    email = request.data.get('email')
    new_password = request.data.get('password')
    
    if not email or not new_password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Ищем пользователя по email
        user = CustomUser.objects.get(email=email)
        # Обновляем пароль
        user.password = new_password  # Пароль задается напрямую, т.к. вы не шифруете
        user.save()  # Сохраняем изменения
        return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    """Класс, описывающий методы работы с пользователями
    Осуществляет связь с таблицей пользователей в базе данных
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    # model_class = CustomUser

    def get_permissions(self):
        if self.action in ['create']:
            permission_classes = [AllowAny]
        elif self.action in ['list']:
            permission_classes = [IsAdmin | IsManager]
        else:
            permission_classes = [IsAdmin]
        return [permission() for permission in permission_classes]

def method_permission_classes(classes):
    def decorator(func):
        def decorated_func(self, *args, **kwargs):
            self.permission_classes = classes        
            self.check_permissions(self.request)
            return func(self, *args, **kwargs)
        return decorated_func
    return decorator

from .serializers import getCargoSerializer
@swagger_auto_schema(method='get',
                     manual_parameters=[
                         openapi.Parameter('title', openapi.IN_QUERY, description="Название услуги для поиска", type=openapi.TYPE_STRING),
                         openapi.Parameter('min_price', openapi.IN_QUERY, description="Минимальная цена", type=openapi.TYPE_STRING),
                     ],
                     responses={
                         status.HTTP_200_OK: getCargoSerializer,
                         
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                     })

@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([AuthIfPos])
def rent_list(request):
    """
    получение списка услуг
    """
    user = request.user
    print(user)
    draft_order = None
    cnt = 0
    if not request.user.is_anonymous:
        draft_order = Addresses.objects.filter(client=user.pk,status=Addresses.StaTus.DRAFT).first()
        if draft_order is not None:
            cnt =  Readings.objects.filter(order_id=draft_order.id).select_related('cargo').count() if draft_order.id is not None else 0
    
    # Получение параметров из запроса
    title = request.query_params.get('title', None)
    print(title)
    min_price = request.query_params.get('min_price', None)
    print(min_price)

    services = Public_Service.objects.all().order_by('id')
    # draft_order = Rent_Order.objects.filter(status=Rent_Order.StaTus.DRAFT).first()
    # Применение фильтров по названию и цене
    if title:
        services = services.filter(title__icontains=title)
    s_services = list(services)
    if min_price == '0':
        # services = services.filter(price__gte=min_price)  # Предполагается, что есть поле price
        try:
            n = len(services)
            for i in range(n):
                # Последние i элементов уже отсортированы, поэтому мы уменьшаем количество итераций
                for j in range(0, n-i-1):
                    # Сравниваем элементы и меняем их местами, если они не в правильном порядке
                    if float(s_services[j].price.split()[0]) > float(s_services[j+1].price.split()[0]):
                        # Меняем элементы местами
                        s_services[j], s_services[j+1] = s_services[j+1], s_services[j]
            # print(22222, [s.price.split()[0] for s in s_services])
            print(s_services)
        except ValueError:
            pass
    serializer = getCargoSerializer({
        'ServiceList' : Rent_ServiceSerializer(s_services,many=True).data,
        'OrderId' :  draft_order.id if draft_order else None,
        'items_in_cart' : cnt
    })
    return Response(serializer.data, status=status.HTTP_200_OK)







@swagger_auto_schema(method='put',
                     responses={
                         status.HTTP_200_OK: Rent_OrderSerializer(),
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['PUT'])
@permission_classes([IsAuthManager])
@authentication_classes([AuthIfPos])
def finalize_order(request, pk=None):
        try:
            order = Addresses.objects.get(pk=pk)

            # Проверка на непустоту обязательных полей
            if not order.order_date or not order.address:
                return Response({"error": "Поля 'Дата создания' и 'Адрес' не могут быть пустыми."}, 
                                status=status.HTTP_400_BAD_REQUEST)

            # Подтверждение заявки создателем
            order.moderator = request.user  # Установка модератора как текущего пользователя
            order.completion_date = datetime.now()
            order.status = Addresses.StaTus.FOMED  # Устанавливаем статус как 'FOMED'
            
            order.save()
            return Response({"message": "Заявка успешно подтверждена и ожидает модерации."}, 
                            status=status.HTTP_200_OK)
        except Addresses.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
from dateutil.parser import parse
@swagger_auto_schema(method='get',
                     manual_parameters=[
                         openapi.Parameter('status',
                                           type=openapi.TYPE_STRING,
                                           description='status',
                                           in_=openapi.IN_QUERY),
                         openapi.Parameter('formation_start',
                                           type=openapi.TYPE_STRING,
                                           description='status',
                                           in_=openapi.IN_QUERY,
                                           format=openapi.FORMAT_DATETIME),
                         openapi.Parameter('formation_end',
                                           type=openapi.TYPE_STRING,
                                           description='status',
                                           in_=openapi.IN_QUERY,
                                           format=openapi.FORMAT_DATETIME),
                     ],
                     responses={
                         status.HTTP_200_OK: Rent_OrderrSerializer(many=True),
                         status.HTTP_403_FORBIDDEN: "Forbidden",})
@api_view(['GET'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def list_order(request):
        
        status_filter = request.query_params.get("status")
        formation_datetime_start_filter = request.query_params.get("formation_start")
        formation_datetime_end_filter = request.query_params.get("formation_end")
        filters = ~Q(status=Addresses.StaTus.DELETED)
        # Получение всех заявок, кроме удаленных и черновиков
        if status_filter is not None:
            filters &= Q(status=status_filter)
        if formation_datetime_start_filter is not None:
            filters &= Q(order_date__gte=parse(formation_datetime_start_filter))
        if formation_datetime_end_filter is not None:
            filters &= Q(completion_date__lte=parse(formation_datetime_end_filter))
        if not request.user.is_superuser:
            filters &= Q(client=request.user.id)
            filters &= ~Q(status=Addresses.StaTus.DRAFT)
        orders = Addresses.objects.filter(filters)
        serializer = Rent_OrderrSerializer(orders, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(method='get',
                     responses={
                         status.HTTP_200_OK: Rent_ServiceSerializer(),
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })

@api_view(['GET'])
@permission_classes([AllowAny])
def Get_Service(request, pk):
    """
    получение услуги
    """
    cargo = Public_Service.objects.filter(id=pk, status='Активна').first()
    if cargo is not None:
        serilizer = Rent_ServiceSerializer(cargo)
        return Response(serilizer.data, status=status.HTTP_200_OK)
    return Response("No such cargo", status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(method='post',
                     request_body=Rent_ServiceSerializer,
                     responses={
                         status.HTTP_200_OK: Rent_ServiceSerializer(),
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                     })

@api_view(['POST'])
@permission_classes([IsAuthManager])
def add_Service(request):
    """
    добавить новую услугу
    """
    print(request.data)
    serializer = Rent_ServiceSerializer(data=request.data)
    if serializer.is_valid():
        cargo = serializer.save()
        serializer = Rent_ServiceSerializer(cargo)
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response('Failed to add service', status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(method='put',
                     request_body=Rent_ServiceSerializer,
                     responses={
                         status.HTTP_200_OK: Rent_ServiceSerializer(),
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })

@api_view(['PUT'])
@permission_classes([IsAuthManager])
def Change_Service(request, pk):
    """
    изменить услугу
    """
    service = Public_Service.objects.filter(id=pk, status='Активна').first()
    if service is None:
        return Response('No such service', status=status.HTTP_404_NOT_FOUND)
    serializer = Rent_ServiceSerializer(service,data=request.data,partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    else:
        return Response('Incorrect data', status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(method='delete',
                     responses={
                         status.HTTP_200_OK: "OK",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })       
@api_view(['DELETE'])
@permission_classes([IsAuthManager])
def Delete_Service(request, pk):
    """
    удалить услугу
    """
    from iu5_web.settings import AWS_S3_ENDPOINT_URL,AWS_STORAGE_BUCKET_NAME,MINIO_USE_SSL,AWS_SECRET_ACCESS_KEY,AWS_ACCESS_KEY_ID
    service = Public_Service.objects.filter(id=pk, status='Активна').first()
    if service is None:
        return Response('No such serviuce', status=status.HTTP_404_NOT_FOUND)
    if service.icon != '':
        storage = Minio(endpoint=AWS_S3_ENDPOINT_URL,access_key=AWS_ACCESS_KEY_ID,secret_key=AWS_SECRET_ACCESS_KEY,secure=MINIO_USE_SSL)
        extension = os.path.splitext(service.icon)[1]
        file = f"{pk}{extension}"
        try:
            print('try')
            storage.remove_object(AWS_STORAGE_BUCKET_NAME, file)
        except Exception as exception:
            print('except')
            return Response(f'Failed to remove pic due to {exception}', status=status.HTTP_400_BAD_REQUEST)
        service.logo_file_path = ""
    service.status = 'Не активна'
    service.save()
    return Response('Succesfully removed the service', status=status.HTTP_200_OK)



@swagger_auto_schema(method='post',
                     responses={
                         status.HTTP_200_OK: "OK",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['POST'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def CreateRentOrder(request, pk):
    """
    создать новое отправление или добавить туда груз
    """
    service = Public_Service.objects.filter(id=pk, status='Активна')
    if service is None:
        return Response('No such cargo', status=status.HTTP_404_NOT_FOUND)
    order_id = get_or_create_order(request.user.id)
    service_order = Readings.objects.filter(
        Q(service_id=pk) & Q(order_id=order_id)
    ).first()
    if not service_order:
        service_order = Readings(order_id = order_id, service_id=pk)
        service_order.save()
    return Response('Succesfully added cargo to shipping')


def get_or_create_order(user_id):
    req = Addresses.objects.filter(client = user_id, status=Addresses.StaTus.DRAFT).first()
    if req is None:
        order = Addresses(client = user_id, status=Addresses.StaTus.DRAFT,  order_date = datetime.now())
        order.save()
        return order.id
    return req.id

@swagger_auto_schema(method="post",
                     manual_parameters=[
                         openapi.Parameter(name="image",
                                           in_=openapi.IN_FORM,
                                           type=openapi.TYPE_FILE,
                                           required=True, description="Image")],
                     responses={
                         status.HTTP_200_OK: "OK",
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                     })
@api_view(['POST'])
@permission_classes([IsAuthManager])
@parser_classes([MultiPartParser])
def load_image_to_minio(request, pk):
    """
    загрузить картинку в минио
    """
    from iu5_web.settings import AWS_S3_ENDPOINT_URL,AWS_STORAGE_BUCKET_NAME,MINIO_USE_SSL,AWS_SECRET_ACCESS_KEY,AWS_ACCESS_KEY_ID
    service = Public_Service.objects.filter(id=pk, status='Активна').first()
    if service is None:
        return Response('No such service', status=status.HTTP_400_BAD_REQUEST)
    
    storage = Minio(endpoint=AWS_S3_ENDPOINT_URL,access_key=AWS_ACCESS_KEY_ID,secret_key=AWS_SECRET_ACCESS_KEY,secure=MINIO_USE_SSL)
    extension = os.path.splitext(service.icon)[1]
    file_name = f'{pk}{extension}'
    file = request.FILES.get("image")
    print(file)
    try:
        storage.put_object(AWS_STORAGE_BUCKET_NAME, file_name, file, file.size)
    except Exception as exception:
        return Response(f'Failed to load pic due to {exception}', status=status.HTTP_400_BAD_REQUEST)
    service.icon = f'http://{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/{file_name}'
    service.save()
    return Response('Succesfully added/changed pic', status=status.HTTP_200_OK)






@swagger_auto_schema(method='get',
                     responses={
                         status.HTTP_200_OK: Rent_Order_with_info_Serializer(),
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['GET'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def get_order(request, pk):
    """
    получить отправление
    """
    filters = Q(id=pk) & ~Q(status=Addresses.StaTus.DELETED)
    order = Addresses.objects.filter(filters).first()
    if order is None:
        return Response('No such shipping', status=status.HTTP_404_NOT_FOUND)
    # изменил модератор на клиент
    if not request.user.is_superuser and order.client != request.user.id:
        print(order.client)
        print(order.pk)
        print(request.user)
        return Response(status=status.HTTP_403_FORBIDDEN)

    serializer = Rent_Order_with_info_Serializer(order)
    return Response(serializer.data, status=status.HTTP_200_OK)




@swagger_auto_schema(method='put',
                     request_body=Rent_OrderSerializer,
                     responses={
                         status.HTTP_200_OK: Rent_OrderSerializer(),
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['PUT'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def change_order(request, pk):
    """
    изменить отправление
    """
    service = Addresses.objects.filter(id=pk, client = request.user.id).first()
    print(request.user.id)
    if service is None:
        return Response('No such service', status=status.HTTP_404_NOT_FOUND)
    print(service)

    serializer = Rent_OrderSerializer(service, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    else:
        return Response('Incorrect data', status=status.HTTP_400_BAD_REQUEST)
    



@swagger_auto_schema(method='put',
                     responses={
                         status.HTTP_200_OK: Rent_OrderSerializer(),
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['PUT'])
@permission_classes([IsAuth])
@authentication_classes([AuthIfPos])
def rejecting_order(request, pk=None):
        try:
            order = Addresses.objects.get(pk=pk)

            # Проверка на непустоту обязательных полей
            if not order.order_date or not order.address:
                return Response({"error": "Поля 'Дата создания' и 'Адрес' не могут быть пустыми."}, 
                                status=status.HTTP_400_BAD_REQUEST)

            # Подтверждение заявки создателем
            order.moderator = request.user.id  # Установка модератора как текущего пользователя
            order.completion_date = datetime.now()
            order.status = Addresses.StaTus.FOMED  # Устанавливаем статус как 'FOMED'
            
            # Пересчет общей стоимости заявки
            # recalculate_total(order)

            order.save()
            return Response({"message": "Заявка успешно оформлена."}, 
                            status=status.HTTP_200_OK)
        except Addresses.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

@swagger_auto_schema(method='delete',
                     responses={
                         status.HTTP_200_OK: "OK",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['DELETE'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def delete_order(request, pk):

    """
    удалить оформление
    """
    order = Addresses.objects.filter(id=pk,status=Addresses.StaTus.DRAFT).first()
    if order is None:
        return Response("No such order", status=status.HTTP_404_NOT_FOUND)
    
    if not request.user.is_superuser and order.client != request.user.id:
        return Response(status=status.HTTP_403_FORBIDDEN)
    order.status = order.StaTus.DELETED
    order.save()
    return Response(status=status.HTTP_200_OK)


def recalculate_total(order : Addresses):
        total = sum([order.service.calculate_amount_due() for service in order.readings_set.all()])
        order.total_amount = total
        order.save()


@swagger_auto_schema(method='delete',
                     responses={
                         status.HTTP_200_OK: "OK",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['DELETE'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def delete_service_from_order(request, sk, ok):
    """
    Удаление груза из отправления
    """

    print(sk, ok)
    service_in_order = Readings.objects.filter(service_id=ok, order_id=sk).first()
    print(ok, sk)
    if service_in_order is None:
        return Response("service not found", status=status.HTTP_404_NOT_FOUND)
    
    if Addresses.objects.filter(id=sk).first().client != request.user.id:
        return Response(status=status.HTTP_403_FORBIDDEN)
    service_in_order.delete()
    order_id = service_in_order.order
    cargo_id = service_in_order.service
    order = Addresses.objects.filter(id=sk).first()
    service = Public_Service.objects.filter(id=ok).first()
    order.save()
    return Response(status=status.HTTP_200_OK)




@swagger_auto_schema(method='put',
                     request_body=Rent_OrderServiceSerializer,
                     responses={
                         status.HTTP_200_OK: Rent_OrderServiceSerializer(),
                         status.HTTP_400_BAD_REQUEST: "Bad Request",
                         status.HTTP_403_FORBIDDEN: "Forbidden",
                         status.HTTP_404_NOT_FOUND: "Not Found",
                     })
@api_view(['PUT'])
@permission_classes([IsAuth])
@authentication_classes([Auth_by_Session])
def change_shipping_cargo(request, sk, ok):
    """
    Изменение данных о грузе в отправлении
    """
    print(ok, sk)
    order = Addresses.objects.filter(id=ok).first()
    print(order)
    if order is None:
        return Response('order not found', status=status.HTTP_404_NOT_FOUND)
    if not request.user.is_superuser and order.client != request.user.id:
        # print(1)
        # print(order.client)
        # print(2)
        # print(request.user.id)
        # print(3)
        # print(request.user)
        return Response(status=status.HTTP_403_FORBIDDEN)
    service_in_order = Readings.objects.filter(service=sk, order=ok).first()
    if service_in_order is None:
        return Response("service not found", status=status.HTTP_404_NOT_FOUND)
    serializer = Rent_OrderServiceSerializer(service_in_order, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    else:
        return Response('Failed to change data', status=status.HTTP_400_BAD_REQUEST)

class RentServiceViewSet(viewsets.ViewSet):
    


    @swagger_auto_schema(responses={200: Rent_ServiceSerializer})
    def retrieve(self, request, pk=None):
        try:
            service = Public_Service.objects.get(pk=pk)
            serializer = Rent_ServiceSerializer(service)
            return Response(serializer.data)
        except Public_Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(request_body=Rent_ServiceSerializer)
    def create(self, request):
        serializer = Rent_ServiceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(request_body=Rent_ServiceSerializer)
    @method_permission_classes((IsAdmin,))
    def update(self, request, pk=None):
        try:
            service = Public_Service.objects.get(pk=pk)
            serializer = Rent_ServiceSerializer(service, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Public_Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
    
    def destroy(self, request, pk=None):
        try:
            service = Public_Service.objects.get(pk=pk)

            # Удаляем изображение из MinIO
            client = Minio(
                endpoint=settings.AWS_S3_ENDPOINT_URL,
                access_key=settings.AWS_ACCESS_KEY_ID,
                secret_key=settings.AWS_SECRET_ACCESS_KEY,
                secure=settings.MINIO_USE_SSL
            )
            img_obj_name = f"{service.id}.svg"  # Имя изображения, основанное на ID услуги

            # Удаляем объект из MinIO
            client.remove_object('lab3', img_obj_name)

            # Удаляем услугу из базы данных
            service.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Public_Service.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def add_to_draft_order(self, request, pk=None):
        draft_order, created = Addresses.objects.get_or_create(
            status=Addresses.StaTus.DRAFT,
            defaults={
                "moderator": "Moderator1",  # автоматически создается
                "formation_date": datetime.now(),
                "order_date": datetime.now(),
            },
        )
        service = Public_Service.objects.get(pk=pk)
        Readings.objects.create(order=draft_order, service=service)
        return Response({"message": "Service added to draft order"}, status=status.HTTP_201_CREATED)


    def add_image(self, request, pk=None):
            try:
                service = Public_Service.objects.get(pk=pk)
                image = request.FILES.get('icon')  # Получаем изображение из запроса
                if image:
                    response = add_pic(service, image)  # Используем функцию для загрузки изображения
                    return response
                return Response({"error": "Нет изображения для загрузки."}, status=status.HTTP_400_BAD_REQUEST)
            except Public_Service.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)


class RentOrderViewSet(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]

    @swagger_auto_schema(responses={200: Rent_OrderSerializer(many=True)})
    def list(self, request):
        # Получение всех заявок, кроме удаленных и черновиков
        orders = Addresses.objects.exclude(status=Addresses.StaTus.DELETED).exclude(status=Addresses.StaTus.DRAFT)
        serializer = Rent_OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @swagger_auto_schema(responses={200: Rent_OrderSerializer})
    def retrieve(self, request, pk=None):
        try:
            order = Addresses.objects.get(pk=pk)
            serializer = Rent_OrderSerializer(order)
            return Response(serializer.data)
        except Addresses.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
    @swagger_auto_schema(request_body=Rent_OrderSerializer)
    @method_permission_classes((IsAdmin,))
    def update(self, request, pk=None):
        try:
            order = Addresses.objects.get(pk=pk)
            serializer = Rent_OrderSerializer(order, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Addresses.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
    
    @swagger_auto_schema(request_body=Rent_OrderSerializer)
    @method_permission_classes((IsAdmin,))
    
    @swagger_auto_schema(request_body=Rent_OrderSerializer)
    def reject(self, request, pk=None):
            try:
                order = Addresses.objects.get(pk=pk)
                order.moderator = request.user
                order.completion_date = datetime.now()
                order.status = Addresses.StaTus.REJECTED
                order.save()
                return Response({"message": "Заявка отклонена."}, status=status.HTTP_200_OK)
            except Addresses.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)


    def destroy(self, request, pk=None):
            try:
                order = Addresses.objects.get(pk=pk)
                order.status = Addresses.StaTus.DELETED
                order.save()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Addresses.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)
            
class RentServiceOrderViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def delete_service_from_order(self, request, order_id, service_id):
        try:
            # Поиск заявки и услуги по их ID
            order_service = Readings.objects.get(order_id=order_id, service_id=service_id)
            
            # Удаляем услугу из заявки
            order_service.delete()
            
            # Пересчитываем общую сумму заявки
            order_service.order.recalculate_total()
            
            return Response({"message": "Услуга успешно удалена из заявки."}, status=status.HTTP_204_NO_CONTENT)
        except Readings.DoesNotExist:
            return Response({"error": "Услуга не найдена в заявке."}, status=status.HTTP_404_NOT_FOUND)
    
    @swagger_auto_schema(
        request_body=Rent_OrderServiceSerializer,
    )
    def update_current_reading(self, request, order_id, service_id):
        try:
            # Поиск услуги в заявке
            order_service = Readings.objects.get(order_id=order_id, service_id=service_id)
            
            # Обновляем поле current_reading
            new_reading = request.data.get('current_reading')
            if not new_reading:
                return Response({"error": "Поле 'current_reading' обязательно для обновления."}, status=status.HTTP_400_BAD_REQUEST)
            
            order_service.current_reading = new_reading
            order_service.save()  # Автоматический пересчет общей стоимости заявки
            
            return Response({"message": "Текущие показания успешно обновлены."}, status=status.HTTP_200_OK)
        except Readings.DoesNotExist:
            return Response({"error": "Услуга не найдена в заявке."}, status=status.HTTP_404_NOT_FOUND)

# # POST регистрация
# class UserRegistrationView(APIView):
#     def post(self, request):
#         username = request.data.get('username')
#         password = request.data.get('password')
#         email = request.data.get('email')
        
#         if not username or not password or not email:
#             return Response({"error": "Все поля обязательны"}, status=status.HTTP_400_BAD_REQUEST)
        
#         if User.objects.filter(username=username).exists():
#             return Response({"error": "Пользователь с таким именем уже существует"}, status=status.HTTP_400_BAD_REQUEST)
        
#         user = User.objects.create_user(username=username, password=password, email=email)
#         user.save()
#         return Response({"message": "Регистрация прошла успешно"}, status=status.HTTP_201_CREATED)
    
# PUT изменение профиля (личный кабинет)

# class UserProfileUpdateView(APIView):
#     # permission_classes = [IsAuthenticated]

#     def put(self, request):
#         user = request.user
#         username = request.data.get('username', user.username)
#         email = request.data.get('email', user.email)

#         if User.objects.filter(username=username).exclude(pk=user.pk).exists():
#             return Response({"error": "Пользователь с таким именем уже существует"}, status=status.HTTP_400_BAD_REQUEST)
        
#         user.username = username
#         user.email = email
#         user.save()
#         return Response({"message": "Профиль обновлен успешно"}, status=status.HTTP_200_OK)
    
# # POST аутентификация
# class UserLoginView(APIView):
#     # @action(detail=False, methods=['post'], url_path='login')
#     def post(self, request):
#         username = request.data.get('username')
#         password = request.data.get('password')

#         user = authenticate(request, username=username, password=password)
#         if user is not None:
#             login(request, user)
#             return Response({"message": "Аутентификация прошла успешно"}, status=status.HTTP_200_OK)
#         else:
#             return Response({"error": "Неверные данные для входа"}, status=status.HTTP_400_BAD_REQUEST)
#         # return Response({"message": "Аутентификация прошла успешно"}, status=status.HTTP_200_OK)
        
# # POST деавторизация

# class UserLogoutView(APIView):
#     # @action(detail=False, methods=['post'], url_path='logout')
#     def post(self, request):
#         # logout(request)  # Удаление сессии пользователя
#         return Response({"message": "Успешная деавторизация."}, status=status.HTTP_200_OK)
    
