"""
AppDaemon narodmon.ru sender script
Credits: @Lefey / https://github.com/Lefey/ad_narodmon_sender
To enable this script add to /config/appdaemon/apps/apps.yaml:
narodmon-sender:
  module: narodmon-sender
  class: narodmon-sender
  narodmon_device_mac: MAC-address to identify your device on narodmon.ru (mandatory)
  narodmon_device_name: Name for your device (optional)
  hass_coordinates_entity: Home assistant zone entity_id for getting latitude and longitude, helps auto placing device on map (optional)
  hass_sensor_entities: Comma-separated home assistant sensor entity_id`s (without spaces)
For example:
narodmon_sender:
  module: narodmon_sender
  class: narodmon_sender
  narodmon_device_mac: AABBCCDDEEFF
  narodmon_device_name: Xiaomi_WSDCGQ01LM
  hass_coordinates_entity: zone.home
  hass_sensor_entities: sensor.outside_temperature,sensor.outside_humidity
"""
import appdaemon.plugins.hass.hassapi as hass
import socket
import datetime
import collections

class narodmon_sender(hass.Hass):
    #метод запускаемый однократно при старте программы
    def initialize(self):
        # объявляем переменные:
        # список сенсоров для отправки
        self.sensors = []
        # словарь имен для сенсоров (берем из friendly_name)
        self.sensors_name = {}
        # словарь типов сенсоров (берем из device_class, если есть)
        self.sensors_type = {}
        # форматированные данные для отправки
        self.data = None
        # словарь замены типов для автоопределения типа сенсора на narodmon.ru, 
        # исходные данные берутся из параметра device_class сенсора, при отсутстви датчики будут именованы как SENSOR#, тип нужно вручную определить на сайте.
        replace = {
            'temperature': 'TEMP',
            'humidity': 'RH',
            'pressure': 'PRESS',
            'battery': 'BATCHARGE',
            'power': 'W',
            'illuminance': 'LIGHT',
            'signal_strength': 'RSSI',
             None: 'SENSOR'
            }
        # проверяем, есть ли переменная с MAC-адресом в параметрах скрипта
        if "narodmon_device_mac" in self.args:
            if self.args["narodmon_device_mac"] != None:
                # начинаем формировать данные для отправки
                self.data = "#" + self.args["narodmon_device_mac"]
                # проверяем наличие названия устройства в параметрах скрипта, добавляем к MAC-адресу, если есть
                if "narodmon_device_name" in self.args:
                    if self.args["narodmon_device_name"] != None:
                        self.data += "#" + self.args["narodmon_device_name"]
                # проверяем наличие зоны в параметрах скрипта для определения координат
                if "hass_coordinates_entity" in self.args:
                    if self.entity_exists(self.args["hass_coordinates_entity"]):
                        lat = self.get_state(self.args["hass_coordinates_entity"], "latitude")
                        lng = self.get_state(self.args["hass_coordinates_entity"], "longitude")
                        if lat != None and lng != None:
                            self.data += "\n#LAT#" + str(lat) + "\n#LNG#" + str(lng)
            else:
                exit("Please, define narodmon_device_mac value in /config/appdaemon/apps/apps.yaml")
        else:
            exit("Please, specify narodmon_device_mac variable in /config/appdaemon/apps/apps.yaml")
        # проверка наличия перечня сенсоров в парамерах скрипта
        if "hass_sensor_entities" in self.args:
            for entity in self.split_device_list(self.args["hass_sensor_entities"]):
                # проверка существования объекта в home assistant
                if self.entity_exists(entity):
                    domain, sensor_id = self.split_entity(entity)
                    # отфильтровываем все кроме сенсоров
                    if domain == "sensor":
                        # заполняем список сенсоров для отправки
                        self.sensors.append(sensor_id)
                        # заполняем словари имен и типов
                        self.sensors_name[sensor_id] = self.get_state(entity, "friendly_name")
                        self.sensors_type[sensor_id] = self.get_state(entity, "device_class")
            # на основе словаря типов переименовываем и нумеруем по порядку повторяющиеся
            for sensor_id in self.sensors_type:
                if self.sensors_type[sensor_id] in replace:
                    self.sensors_type[sensor_id] = replace[self.sensors_type[sensor_id]]
            count = collections.Counter(self.sensors_type.values())
            for type in count:
                if count[type] > 1:
                    num = count[type]
                    sel = 1
                    for sensor_id in self.sensors_type:
                        if self.sensors_type[sensor_id] == type:
                            self.sensors_type[sensor_id] = type + str(range(num + 1)[sel])
                            sel = sel + 1
        else:
            exit("Please, specify hass_sensor_entities variable in /config/appdaemon/apps/apps.yaml")
        # вызвываем метод отправки данных каждые 5 минут, начиная с текушего времени 
        self.run_every(self.send_data, datetime.datetime.now() + datetime.timedelta(seconds=2), 300)
    # метод для отправки данных
    def send_data(self, kwargs):
        # проверяем, есть ли данные для отправки
        if self.data != None:
            for sensor_id in self.sensors:
                # отбрасываем недоступные датчики
                if self.get_state('sensor.' + sensor_id) != 'unavailable':
                    # добавляем к строке с общей информацией данные всех рабочих сенсоров
                    self.data += "\n#" + self.sensors_type[sensor_id] + "#" + self.get_state('sensor.' + sensor_id) + "#" + self.sensors_name[sensor_id]
            self.data += "\n##"
            # вывод в лог информации которая будет отправлена
            self.log("Data for send to narodmon.ru:\n" + str(self.data))
            # создаем сокет для подключения к narodmon.ru
            sock = socket.socket()
            try:
                # пробуем подключиться
                sock.connect(("narodmon.ru", 8283))
                # пишем в сокет значения датчиков
                sock.send(self.data.encode('utf-8'))
                # читаем ответ сервера
                reply = sock.recv(1024)
                sock.close()
                self.log("narodmon.ru server reply: " + str(reply))
            except socket.error as err:
                self.error("Got error when connecting narodmon.ru: " + str(err))
        else:
            exit("No data for send to narodmon.ru")
