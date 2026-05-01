import sys
sys.path.append("/home/hfy/APP/All_bot")
from src.filters.i18n_filter import I18nFilter
f = I18nFilter(["menu.photo_edit_undress"])
print("I18nFilter imported and instantiated successfully!")
