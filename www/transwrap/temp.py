# coding=utf-8
import requests

dirname2 = 'D:\\'

dirname = r'C:\Users\dell\Desktop\test\awesome-blog\www\static\avatar'

dirname3 = r'C:\Users\dell\Desktop\html文件'

dirname4 = r'C:\Users\dell\Desktop\test'
content = requests.get('http://avatar.csdn.net/D/B/5/1_john2522.jpg').content

with open(dirname+'\\'+'test.jpg', 'wb') as f:
    f.write(content)