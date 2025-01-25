import configparser
import os
import requests
import json
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload
from tqdm import tqdm

local_folder = 'images'
folder_name = "NETOLOGY_TASK"

config = configparser.ConfigParser()
config.read('settings.ini')

vk_token = config['VK']['token_vk'].strip()
vk_user_id = config['VK']['user_id_vk'].strip()
ya_token = config['Yandex']['token_ya'].strip()

if not config.sections():
    print("Файл settings.ini не найден или пуст.")
else:
    print("Файл settings.ini успешно загружен.")
    print("Секции:", config.sections())

class VKAPI():
    #Класс для сбора фотографий из ВК
    API_URL = "https://api.vk.com/method/"

    def __init__(self, token_vk, user_id_vk, version="5.199"):
        self.token_vk = token_vk
        self.user_id_vk = user_id_vk
        self.version = version
        self.uploaded_files = []
    
    def _get_params_vk(self):
        return {
            "access_token" : self.token_vk,
            "v" : self.version
        }

    def get_photos(self):
        params = self._get_params_vk()
        params.update({
            "album_id": "profile",
            "owner_id": f"{self.user_id_vk}",
            "extended": "1"
        })
        response = requests.get(f"{self.API_URL}/photos.get", params=params)

        if "error" in response:
            error_msg = response["error"]["error_msg"]
            print(f"Ошибка API ВКонтакте: {error_msg}")
            print()
            return []

        url = response.json()["response"]["items"]
        filenames = []
        likes = [likes["likes"]["count"] for likes in url if 'likes' in likes]
        image = [image['orig_photo']["url"] for image in url if 'orig_photo' in image]
        zipped = list(zip(image,likes))

        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
            print(f"Папка `{local_folder}` создана")
            print()
        else:
            print(f"Папка `{local_folder}` уже существует!")
            
        for img, name in tqdm(zipped, desc="Загрузка фотографий из ВК", position=0):
            filename = f"{name}.jpg"
            download_img = requests.get(img)
            with open(local_folder + "/" + filename, 'wb') as f:
                f.write(download_img.content)
            filenames.append(filename)

            self.uploaded_files.append({
                "file_name": filename,
                "size": os.path.getsize(local_folder + "/" + filename)
            })

        print(f"Фотографии загружены в папку {local_folder}")
        print()
        self._create_json_report()
        return filenames
    
    def _create_json_report(self):
        with open("uploaded_files.json", "w") as json_file:
            json.dump(self.uploaded_files, json_file, ensure_ascii=False, indent=4)
        print("Информация о загруженных файлах сохранена в uploaded_files.json")
        print()

class YAAPI():
    #Класс для создания папки и загрузки фотографий на Яндекс Диск, скачанных ранее из ВК
    DISK_URL = "https://cloud-api.yandex.net/v1/disk/resources"
    UPLOAD_URL = "https://cloud-api.yandex.net/v1/disk/resources/upload"

    def __init__(self, token_ya):
        self.token_ya = token_ya

    def _get_params_yadisk(self):
        return {"path": f"{folder_name}"}
    
    def _get_header_yadisk(self):
        return {'Authorization': f'OAuth {self.token_ya}'}

    def _create_folder(self):
        params = self._get_params_yadisk()
        headers = self._get_header_yadisk()
        response = requests.put(self.DISK_URL, params=params, headers=headers)
        if response.status_code == 201:
            print("Папка в YandexDisk создана или уже существует")
        else:
            print("Ошибка при создании папки в YandexDisk:", response.json()['message'])
            print()
    
    def upload_images(self, filenames):
        self._create_folder()
        for filename in tqdm(filenames, desc="Загрузка на Яндекс.Диск", position=1):
            params = self._get_params_yadisk()
            headers = self._get_header_yadisk()
            params.update({"path": f"{folder_name}/{filename}"})
            response = requests.get(self.UPLOAD_URL, params=params, headers=headers)
            if 'href' in response.json():
                upload_url = response.json()['href']
                with open(f"images/{filename}", 'rb') as f:
                    response = requests.put(upload_url, files={'file': f})
                    print(f"Загрузка фотографии {filename} в YandexDisk завершена:", response.status_code)
            else:
                print(f"Ошибка загрузки фотографии {filename} в YandexDisk: {response.json()['message']}")
                print()
        print()
        return None

class GoogleDriveAPI():
    #Класс для создания папки и загрузки фотографий на Google Диск, скачанных ранее из ВК
    """ДЛЯ РАБОТЫ МЕТОДА ТРЕБУЕТСЯ ПРЕДВАРИТЕЛЬНОЕ ПОЛУЧЕНИЕ ТОКЕНА И НАЛИЧИЕ В ПАПКЕ ФАЙЛА credentials.json
        https://console.cloud.google.com/apis/credentials
    """
    DRIVE_URL = "https://www.googleapis.com/auth/drive"

    def __init__(self, token_gdrive = ""):
        self.token_gdrive = token_gdrive

    def _authenticate(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    print("Файл credentials.json отсутствует")
                    return None
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.DRIVE_URL)
                creds = flow.run_local_server(port=0)
            # Сохранение учетных данных в token.pickle
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        return build('drive', 'v3', credentials=creds)

    def _create_folder(self):
        """Проверка на существование папки по имени. Если существует, возвращает её ID, иначе создаёт новую папку."""
        service = self._authenticate()
        if service is None:
            exit(1)
        results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'", 
                                       fields="files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print(f"Папка '{folder_name}' не найдена. Создаём новую.")
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            print(f"Папка '{folder_name}' в GoogleDisk создана. ID: {folder.get('id')}")
            print()
            return folder.get('id')
        else:
            folder_id = items[0]['id']
            print(f"Папка '{folder_name}' в GoogleDisk уже существует. ID: {folder_id}")
            print()
            return folder_id
    
    def upload_images(self, filenames):
        """Загрузка файлов из папки images на Google Диск."""
        service = self._authenticate()
        folder_id = self._create_folder()

        for filename in tqdm(filenames, desc="Загрузка на Google Диск", position=2):
            file_path = f"images/{filename}"
            if os.path.exists(file_path):
                file_metadata = {
                    'name': filename,
                    'parents': [folder_id]
                }
                media = MediaFileUpload(file_path, resumable=True)
                file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                print(f"Файл '{filename}' успешно загружен в GoogleDisk. ID: {file.get('id')}")
            else:
                print(f"Файл '{filename}' не найден в локальной папке images.")


if __name__ == "__main__":
    vk_client = VKAPI(vk_token, vk_user_id)
    ya_client = YAAPI(ya_token)
    google_drive_client = GoogleDriveAPI()

    photo = vk_client.get_photos()
    upload_images_to_ya = ya_client.upload_images(photo)
    if os.path.isfile("credentials.json"):
        upload_images_to_google = google_drive_client.upload_images(photo)
        print()
    else:
        print("Файл credentials.json отсутствует, загрузка файла на GoogleDisk пропущена")
        print()