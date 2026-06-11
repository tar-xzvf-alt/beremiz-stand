# Beremiz Project

`study-plc/` создан штатным API установленного Beremiz (`ProjectController.NewProject`) и является начальным пустым PLC-проектом стенда.

Открытие в IDE:

```bash
beremiz beremiz-project/study-plc
```

CLI-проверка загрузки проекта:

```bash
/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc clean
```

`build/` внутри проекта является рабочим каталогом Beremiz и не хранится в git.
