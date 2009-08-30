def lru_decorate(max_len, keep_record=False, hashfunc=None, keep_time=None):
    """This is a decorator to be used with a fuction. It grabs the functions
    incoming arguments, (tries) to hash them, and stores the result in the LRU
    for later use. If the arguments should not be hashable, the exception is
    caught and the result directly returned (so if you are unsure, do try
    with keep_record=True and see if there are errors accumulated).
    
    Arguments:
        o max_len: Maximum lengths of the LRU
        o keep_record: If keep_record is not False, then a class will be created
            which keeps the extra arguments .hits, .misses and .errors for
            diagnosis on efficency.
        o hashfunc: A function f with f(*args, **kwargs) is defined, so that
            f gives back a hashable object for *args and **kwargs to identify
            the unique function call. This can also speed up a little, if the
            function is simple.
        o keep_time: If given, a TimedLRU is created, where all items have a
            time, and are kept at least keep_time long in the LRU.
    
    WARNING: The default hashfunc will use (args,) or if there are any kwargs
        (args, sorted_list(kwargs.items())). It is not aware of default values,
        and obviously not aware of any other internal changes in the function.
        Make sure to:
            (1) Pass ALL things effecting the outcome into the function with
                args/kwargs and don't create random values, etc. inside.
            (2) Make sure that values you give in are hashable, or set a
                hashfunc that will make them hashable. Check with kee_record
                that there are no or fiew errors (which indicate failed hash).
            (3) Using your own hashfunc that is specialized to your problem is
                often smart. If you are having problems with unhashable objects
                cPickle.dumps might help you out.
    
    USAGE:
    ======
    
    @lru.decorate(50) # 50 item LRU
    def spam(*args, **kwargs):
        eggs = 'Some slow calculation'
        return eggs
    
    # or alternatively:
    @lru.decorate(50, True)
    def spam(*args, **kwargs):
        return args, kwargs
    
    # Some code
    
    print 'Hits:', spam.hits
    print 'Misses:', spam.misses
    print 'Unhashable:', spam.errors
    """
    
    def create_lru(get_func):
        if keep_time is None:
            return LRU(max_len, [], get_func, keep_record, hashfunc)
        else:

            return TimedLRU(max_len, [], get_func, keep_record, hashfunc, keep_time)
    
    return create_lru


class LRU(object):
    """Implemenation of a length-limited least recently used (LRU) queue.
    It works mostly like a dictionary, but only keeps a maximum of max_len
    items around. Old items are discarted automatically.
    
    This LRU assumes that getting the first element is relatively rare, it will
    be outperformed in this cornercase by other implementations out there.
    If you know that getting the first element happens often, check the code.
    
    NOTE: If a get_func is given, calling the LRU will call the LRU wrapped
        function (also available through the decorator as mentioned). The
        LRU[item] = 'asdf', etc. is available, but you need to use hashfunc
        LRU[hashfunc(*args, **kwargs)] for it to work correctly, and it will
        not fallback to the function!
    """
    # As mentioned, to make sure of shortcutting for the first element, you can
    # add some ifs. Look for the "# Unlink the item:" comment. Its there a
    # couple of times, you can add something like if start[3] == item: ...
    
    
    # As a side note. One might wonder why not to use DictMixin, and thats
    # a valid point, but I wanted to use __slots__ as they also increase
    # speed a tiny bit, and DictMixin doesn't use slots.
    __slots__ = ['_items', '_length', '_max_len', '_start', '_end', '__init__',
                 '__setitem__', '__getitem__', 'dict_get', 'dict_set',
                 '__delitem__', '_delete', '__len__', 'iterkeys', 'itervalues',
                 'iteritems', '__iter__', 'keys', 'has_key', '__contains__',
                 'decorate', '_get_func', '__call__', '_key_creater',
                 'misses', 'hits', 'errors', '_call_rec', '_call_norec', 
                 '_hashfunc', '__repr__', '__weakref__']       
    
    
    def __init__(self, max_len, pairs=[], get_func=None, keep_record=False,
                       hashfunc=None):
        """Initialize the LRU of lengths max_len, with pairs of (key, value).
        
        The other intialization are if you want to wrap a function. This is
        useful with the decorate function in the module, please see its
        documentation.
        """
        # Start and end point of the LRU are itself "parts" of it, though
        # they are not saved in the dictionary. This saves some annoying ifs
        # lateron, as the first and last real item are nothing special.
        self._start = [None] * 4
        self._end = [None] * 4
        self._start[3] = self._end # its now: [None, None, None, self._end],
        self._end[2] = self._start # and: [None, None, self._start, None]
        
        # Dictionary of the actual items. The dictionary stores lists:
        # [key, value, prev_item, next_item]. So while reading always keep in
        # mind: 2 == the previous item (yes, the full list) and 3 is the next! 
        self._items = {}
        
        self._max_len = max_len
        self._length = 0
        
        if get_func:
            self.__repr__ = lambda: '<LRU wrapped %s>' % (get_func,)
            self._get_func = get_func
            if keep_record:
                self.hits = 0
                self.misses = 0
                self.errors = 0
                self.__call__ = self._call_rec
            else:
                self.__call__ = self._call_norec
        
        if not hashfunc:
            def hashfunc(*args, **kwargs):
                if not kwargs:
                    return (args,)
                else:
                    # In CPython, items seems to be faster then iteritems
                    # for small lists (which we have).
                    l = kwargs.items()
                    l.sort()
                    return (args, tuple(l))
       
        self._hashfunc = hashfunc
        
        for key, value in pairs:
            self[key] = value
     

    def __setitem__(self, key, value):
        # As further down, these assignments, slightly improve speed, as less
        # lookups are necessary (but assignment overhead is created too):
        items = self._items
        start = self._start
        
        if not key in items:
            if self._length == self._max_len:
                self._delete(self._end[2])
            self._length += 1
            
            # Create correct new item:
            item = [key, value, start, start[3]]
            items[key] = item
        else:
            item = items[key]
            
            # Set the item vor dictionary like mode in case its changed:
            item[1] = value
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]
            
            # Modify item in place (saves another fiew cycles):
            item[2] = start
            item[3] = start[3]
        
        # Modify start and old first value:
        start[3][2] = item
        start[3] = item  
    
    
    def __getitem__(self, key):
        item = self._items[key]
        start = self._start
        
        # Unlink the item:
        item[2][3] = item[3]
        item[3][2] = item[2]   
        
        # New items positional info:
        item[2] = start
        item[3] = start[3]
        
        # Modify start and old first value:
        start[3][2] = item
        start[3] = item
        
        return item[1]


    #####
    # Functions for use in decorator/function wrapping mode:
    #####
    
    def _call_rec(self, *args, **kwargs):
        # The time used in the if is relatively small. This is a speed
        # tradeoff to make non-kwarg function calls a little faster.
        key = self._hashfunc(*args, **kwargs)
        
        try:
            item = self._items[key]
            start = self._start
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]   
            
            # New items positional info:
            item[2] = start
            item[3] = start[3]
            
            # Modify start and old first value:
            start[3][2] = item
            start[3] = item
            self.hits += 1
            
            return item[1]
        
        # We don't have it calculated:
        except KeyError:
            self.misses += 1
            value = self._get_func(*args, **kwargs)
            self.__setitem__(key, value)
            return value
        
        # The key is not hashable:
        except TypeError:
            self.errors += 1
            return self.get_func(*args, **kwargs)


    def _call_norec(self, *args, **kwargs):
        # The time used in the if is relatively small. This is a speed
        # tradeoff to make non-kwarg function calls a little faster.
        key = self._hashfunc(*args, **kwargs)
        
        try:
            item = self._items[key]
            start = self._start
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]   
            
            # New items positional info:
            item[2] = start
            item[3] = start[3]
            
            # Modify start and old first value:
            start[3][2] = item
            start[3] = item
            
            return item[1]
        
        # We don't have it calculated:
        except KeyError:
            value = self._get_func(*args, **kwargs)
            self.__setitem__(key, value)
            return value
        
        # The key is not hashable:
        except TypeError:
            return self.get_func(*args, **kwargs)


    #####
    # Functions to be able to set a key quietly:
    #####
    
    def dict_get(self, key):
        """Get an item without reordering.
        """
        return self._items[key][1]
    
    
    def dict_set(self, key, value):
        """Set an item without reordering (This throws an execption if the key
        is not part of the LRU).
        """
        item = self._items[key]
        item[1] = value
    
    
    def __delitem__(self, key):
        self._delete(self._items[key])
    
    
    #####
    # Delete:
    #####
    
    def _delete(self, item):
        # Unlink the item:
        item[2][3] = item[3]
        item[3][2] = item[2]
        
        # And delete it:
        del self._items[item[0]]
        self._length -= 1
    
    
    #####
    # Some utils:
    #####
    
    def __len__(self):
        """Return the current lengths of the LRU.
        """
        return self._length
    
        
    def iterkeys(self):
        """Return an iterator over keys, starting with the last used item.
        """
        item = self._start[3]
        while item[3] is not None:
            yield item[0]
            item = item[3]
    
    __iter__ = iterkeys
    
    def iteritems(self):
        """Return an iterator over (key, value), starting with last used item.
        """
        item = self._start[3]
        while item[3] is not None:
            yield item[0], item[1]
            item = item[3]
    
    def itervalues(self):
        """Return an iterator over values, starting with the last used item.
        """
        item = self._start[3]
        while item[3] is not None:
            yield item[1]
            item = item[3]
            
    
    def keys(self):
        """Return list of keys stored.
        """
        return self._items.keys()

        
    def has_key(self, key):
        """Check if the LRU contains the key.
        """
        return key in self._items
    
    __contains__ = has_key


class TimedLRU(LRU):
    """This timed LRU is the same as the normal LRU, however it has additionally
    a keep_time.    
    If the oldest item is less then keep_time old, then the new item
    will not be cached. This is for usecases when it might happen that
    more then the LRU size is gotten within a short amount of time, however
    the order does not significantly change. In this case the whole cache stays
    useful for the next refresh cycle, instead of having only the end of the
    last refresh cached while the start is loaded into it.
    """
    
    __slots__ = ['keep_time', '_time']
    
    
    def __init__(self, max_len, pairs=[], get_func=None, keep_record=False,
                       hashfunc=None, keep_time=0.5):
        """Additional to the normal LRU (see its docu please), this one
        takes the argument keep_time in seconds, which is the time that the
        oldest item has to have been inside the LRU before it will be discarted
        for a newer item.
        """
        from time import time
        self._time = time
        
        # Start and end point of the LRU are itself "parts" of it, though
        # they are not saved in the dictionary. This saves some annoying ifs
        # lateron, as the first and last real item are nothing special.
        self._start = [None] * 5
        self._end = [None] * 5
        self._start[3] = self._end
        self._end[2] = self._start
        self.keep_time = keep_time
        
        # Dictionary of the actual items. The dictionary stores lists:
        # [key, value, prev_item, next_item]. So while reading always keep in
        # mind: 2 == the previous item (yes, the full list) and 3 is the next! 
        self._items = {}
        
        self._max_len = max_len
        self._length = 0
        
        if get_func:
            self.__repr__ = lambda: '<LRU wrapped %s>' % (get_func,)
            self._get_func = get_func
            if keep_record:
                self.hits = 0
                self.misses = 0
                self.errors = 0
                self.__call__ = self._call_rec
            else:
                self.__call__ = self._call_norec
        
        if not hashfunc:
            def hashfunc(*args, **kwargs):
                if not kwargs:
                    return (args,)
                else:
                    # In CPython, items seems to be faster then iteritems
                    # for small lists (which we have).
                    l = kwargs.items()
                    l.sort()
                    return (args, tuple(l))
       
        self._hashfunc = hashfunc
        
        for key, value in pairs:
            self[key] = value
    
    #####
    # NOTE: THIS IS BORING, its just the same as before, just with the time
    # check.
    #####
    
    def __setitem__(self, key, value):
        # As further down, these assignments, slightly improve speed, as less
        # lookups are necessary (but assignment overhead is created too):
        items = self._items
        start = self._start
        
        if not key in items:
            if self._length == self._max_len:
                if self._time() - self._end[2][4] < self.keep_time:
                    return
                self._delete(self._end[2])
            self._length += 1
            
            # Create correct new item:
            item = [key, value, start, start[3], self._time()]
            items[key] = item
        else:
            item = items[key]
            
            # Set the item vor dictionary like mode in case its changed:
            item[1] = value
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]
            
            # Modify item in place (saves another fiew cycles):
            item[2] = start
            item[3] = start[3]
            
            # Update the items access time:
            item[4] = self._time()
        
        # Modify start and old first value:
        start[3][2] = item
        start[3] = item  
    
    
    def __getitem__(self, key):
        item = self._items[key]
        start = self._start
        
        # Unlink the item:
        item[2][3] = item[3]
        item[3][2] = item[2]   
        
        # New items positional info:
        item[2] = start
        item[3] = start[3]
        
        # Modify start and old first value:
        start[3][2] = item
        start[3] = item
        
        # Update the items access time:
        item[4] = self._time()
        
        return item[1]


    #####
    # Functions for use in decorator/function wrapping mode:
    #####
    
    def _call_rec(self, *args, **kwargs):
        # The time used in the if is relatively small. This is a speed
        # tradeoff to make non-kwarg function calls a little faster.
        key = self._hashfunc(*args, **kwargs)
        
        try:
            item = self._items[key]
            start = self._start
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]   
            
            # New items positional info:
            item[2] = start
            item[3] = start[3]
            
            # Modify start and old first value:
            start[3][2] = item
            start[3] = item
            
            # Update the items access time:
            item[4] = self._time()
                        
            self.hits += 1
            
            return item[1]
        
        # We don't have it calculated:
        except KeyError:
            self.misses += 1
            value = self._get_func(*args, **kwargs)
            self.__setitem__(key, value)
            return value
        
        # The key is not hashable:
        except TypeError:
            self.errors += 1
            return self.get_func(*args, **kwargs)


    def _call_norec(self, *args, **kwargs):
        # The time used in the if is relatively small. This is a speed
        # tradeoff to make non-kwarg function calls a little faster.
        key = self._hashfunc(*args, **kwargs)
        
        try:
            item = self._items[key]
            start = self._start
            
            # Unlink the item:
            item[2][3] = item[3]
            item[3][2] = item[2]   
            
            # New items positional info:
            item[2] = start
            item[3] = start[3]
            
            # Modify start and old first value:
            start[3][2] = item
            start[3] = item
        
            # Update the items access time:
            item[4] = self._time()
            
            return item[1]
        
        # We don't have it calculated:
        except KeyError:
            value = self._get_func(*args, **kwargs)
            self.__setitem__(key, value)
            return value
        
        # The key is not hashable:
        except TypeError:
            return self.get_func(*args, **kwargs)

