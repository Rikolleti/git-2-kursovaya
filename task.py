import requests
import json
import os
import pickle
from tqdm import tqdm
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload

save_path = 'images/'
folder_name = "NETOLOGY_TASK"

class VKAPI():
    #Класс для сбора фотографий из ВК
    API_URL = "https://api.vk.com/method/"

    def __init__(self, token_vk, user_id_vk):
        self.token_vk = token_vk
        self.user_id_vk = user_id_vk
        self.uploaded_files = []
    
    def get_params_vk(self):
        return {
            "access_token" : self.token_vk,
            "v" : "5.199"
        }

    def get_photos(self):
        params = self.get_params_vk()
        params.update({"album_id": "profile", "extended": "1"})
        response = requests.get(f"{self.API_URL}/photos.get", params=params)
        url = response.json()["response"]["items"]
        filenames = []
        likes = [likes["likes"]["count"] for likes in url if 'likes' in likes]
        image = [image['orig_photo']["url"] for image in url if 'orig_photo' in image]
        zipped = list(zip(image,likes))

        for img, name in tqdm(zipped):
            filename = f"{name}.jpg"
            download_img = requests.get(img)
            with open(save_path + filename, 'wb') as f:
                f.write(download_img.content)
            filenames.append(filename)

            self.uploaded_files.append({
                "file_name": filename,
                "size": os.path.getsize(save_path + filename)
            })

        print("Фотографии загружены")
        self.create_json_report()
        return filenames
    
    def create_json_report(self):
        with open("uploaded_files.json", "w") as json_file:
            json.dump(self.uploaded_files, json_file, ensure_ascii=False, indent=4)
        print("Информация о загруженных файлах сохранена в uploaded_files.json")

class YAAPI(VKAPI):
    #Класс для создания папки и загрузки фотографий на Яндекс Диск, скачанных ранее из ВК
    DISK_URL = "https://cloud-api.yandex.net/v1/disk/resources"
    UPLOAD_URL = "https://cloud-api.yandex.net/v1/disk/resources/upload"

    def __init__(self, token_ya):
        super().__init__(token_vk=None, user_id_vk=None)
        self.token_ya = token_ya

    def get_params_yadisk(self):
        return {"path": f"{folder_name}"}
    
    def get_header_yadisk(self):
        return {'Authorization': f'OAuth {self.token_ya}'}

    def create_folder(self):
        params = self.get_params_yadisk()
        headers = self.get_header_yadisk()
        response = requests.put(self.DISK_URL, params=params, headers=headers)
        if response.status_code == 201:
            print("Папка создана или уже существует")
        else:
            print("Ошибка при создании папки:", response.json())
    
    def upload_images(self, filenames):
        self.create_folder()
        for filename in tqdm(filenames):
            params = self.get_params_yadisk()
            headers = self.get_header_yadisk()
            params.update({"path": f"{folder_name}/{filename}"})
            response = requests.get(self.UPLOAD_URL, params=params, headers=headers)
            if 'href' in response.json():
                upload_url = response.json()['href']
                with open(f"images/{filename}", 'rb') as f:
                    response = requests.put(upload_url, files={'file': f})
                    print(f"Загрузка {filename} завершена:", response.status_code)
            else:
                print(f"Ошибка загрузки {filename}: {response.json()}")
        return None

class GoogleDriveAPI(VKAPI):
    #Класс для создания папки и загрузки фотографий на Google Диск, скачанных ранее из ВК
    """ДЛЯ РАБОТЫ МЕТОДА ТРЕБУЕТСЯ ПРЕДВАРИТЕЛЬНОЕ ПОЛУЧЕНИЕ ТОКЕНА И НАЛИЧИЕ В ПАПКЕ ФАЙЛА credentials.json
        https://console.cloud.google.com/apis/credentials
    """
    DRIVE_URL = "https://www.googleapis.com/auth/drive"

    def __init__(self, token_gdrive):
        self.token_gdrive = token_gdrive

    def authenticate(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.DRIVE_URL)
                creds = flow.run_local_server(port=0)
            # Сохранение учетных данных в token.pickle
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        return build('drive', 'v3', credentials=creds)

    def create_folder(self):
        """Проверка на существование папки по имени. Если существует, возвращает её ID, иначе создаёт новую папку."""
        service = self.authenticate()
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
            print(f"Папка '{folder_name}' создана. ID: {folder.get('id')}")
            return folder.get('id')
        else:
            folder_id = items[0]['id']
            print(f"Папка '{folder_name}' уже существует. ID: {folder_id}")
            return folder_id
    
    def upload_images(self, filenames):
        """Загрузка файлов из папки images на Google Диск."""
        service = self.authenticate()
        folder_id = self.create_folder()

        for filename in tqdm(filenames):
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
                print(f"Файл '{filename}' успешно загружен. ID: {file.get('id')}")
            else:
                print(f"Файл '{filename}' не найден в локальной папке images.")


if __name__ == "__main__":

    vk_client = VKAPI("TOKEN", "USER_ID")
    ya_client = YAAPI("TOKEN")

    google_drive_client = GoogleDriveAPI("")
    photo = vk_client.get_photos()
    upload_images_to_ya = ya_client.upload_images(photo)
    upload_images_to_google = google_drive_client.upload_images(photo)