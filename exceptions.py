class AwairElementBaseClass(Exception):
    pass



class ConnectionFailedException(AwairElementBaseClass):
    def __init__(self, message:str):
        super().__init__(message)
        

class ConnectionTimeoutException(AwairElementBaseClass):
    def __init__(self, message:str):
        super().__init__(message)
        
        

class UnknownException(AwairElementBaseClass):
    def __init__(self, message:str):
        super().__init__(message)