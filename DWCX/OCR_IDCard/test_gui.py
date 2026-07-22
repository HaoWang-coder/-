import tkinter as tk
from tkinter import ttk

try:
    root = tk.Tk()
    root.title("测试窗口")
    root.geometry("400x300")
    
    label = ttk.Label(root, text="GUI测试成功！")
    label.pack(pady=20)
    
    root.mainloop()
except Exception as e:
    print(f"GUI启动失败: {str(e)}")