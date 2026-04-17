import logging

def foo():
    try:
        logging.getLogger(__name__)
    except Exception as e:
        print(repr(e))
    import logging

foo()
