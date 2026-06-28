import time


def calc_time(func):
    """
    Decadorador para calulcar timepo de ejecucion de los proceso
    """

    def funcion_medida(*args, **kwargs):
        time_start = time.time()
        original = func(*args, **kwargs)
        time_end = time.time()
        time_total = time_end - time_start
        print(f'Se ha realizadon en: {time_total:.0f}s')
        return original

    return funcion_medida
