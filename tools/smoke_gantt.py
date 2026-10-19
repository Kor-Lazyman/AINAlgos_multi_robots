"""Pillow Gantt renderer for deterministic scheduler smoke tests."""
def chart(destination, rows, title):
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGB',(1400,310),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',16)
    draw.text((20,15),title,fill='black',font=font)
    colors={'D':'#ed8936','T':'#3182ce','W':'#a0aec0'}
    end=max(r[-1][0] for r in rows)
    for r,own in enumerate(rows):
        y=70+r*60;draw.text((20,y),'R'+str(r+1),fill='black',font=font)
        for a,b in zip(own,own[1:]):
            draw.rectangle((90+a[0]/end*1260,y,90+b[0]/end*1260,y+30),fill=colors[a[4]])
    draw.text((90,255),f'0 s                         Orange: deposition | Blue: travel | Gray: wait                         End: {end:.3f} s',fill='black',font=small)
    image.save(destination/'gantt.png')

