import base64
from PIL import Image
from io import BytesIO

def resize_and_encode(path):
    img = Image.open(path).convert('RGBA')
    img.thumbnail((64, 64))
    buffered = BytesIO()
    img.save(buffered, format='PNG')
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

user_b64 = resize_and_encode('frontend/src/assets/user_avatar.png')
bot_b64 = resize_and_encode('frontend/src/assets/bot_avatar.png')

with open('frontend/src/assets/avatars.ts', 'w') as f:
    f.write(f'export const userAvatarB64 = "data:image/png;base64,{user_b64}";\n')
    f.write(f'export const botAvatarB64 = "data:image/png;base64,{bot_b64}";\n')
print('Avatars generated in avatars.ts')
