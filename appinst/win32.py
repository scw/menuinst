# Copyright (c) 2008-2011 by Enthought, Inc.
# All rights reserved.

import os
import sys
from os.path import exists, join

import wininst
import win32_common as common


def quoted(s):
    """
    quotes a string if necessary.
    """
    # strip any existing quotes
    s = s.strip('"')
    if ' ' in s:
        return '"%s"' % s
    else:
        return s


class Win32(object):
    """
    A class for application installation operations on Windows.

    """
    desktop_dir = common.get_desktop_directory()
    quicklaunch_dir = common.get_quick_launch_directory()

    #==========================================================================
    # Public API methods
    #==========================================================================

    def install_application_menus(self, menus, shortcuts, mode,
                                  uninstall=False):
        """
        Install application menus.

        """
        self._uninstall = uninstall

        # Determine whether we're adding desktop and quicklaunch icons.  These
        # default to yes if we don't have our custom_tools install metadata.
        try:
            from custom_tools.msi_property import get
            self.addtodesktop = bool(get('ADDTODESKTOP') == '1')
            self.addtolauncher = bool(get('ADDTOLAUNCHER') == '1')
        except ImportError:
            self.addtodesktop = True
            self.addtolauncher = True

        if mode == 'system':
            start_menu = common.get_all_users_programs_start_menu()
        else:
            start_menu = common.get_current_user_programs_start_menu()

        if self._uninstall:
            self._uninstall_application_menus(menus, shortcuts, start_menu)
        else:
            self._install_application_menus(menus, shortcuts, start_menu)


    def uninstall_application_menus(self, menus, shortcuts, mode):
        """
        Uninstall application menus.
        """
        self.install_application_menus(menus, shortcuts, mode,
                                       uninstall=True)

    #==========================================================================
    # Internal API methods
    #==========================================================================

    def _install_application_menus(self, menus, shortcuts, start_menu):
        # First build all the requested menus.  These simply correspond to
        # directories on Win32 systems.  Note that we need to build a map from
        # the menu's category to it's path on the filesystem so that we can put
        # the shortcuts in the right directories later.
        self.category_map = {}
        queue = [(menu_spec, start_menu,'') for menu_spec in menus]
        while len(queue) > 0:
            menu_spec, parent_path, parent_category = queue.pop(0)

            # Create the directory that represents this menu.
            path = join(parent_path, menu_spec['name'])
            if not exists(path):
                os.makedirs(path)

            # Determine the category for this menu and record it in the map.
            # Categories are always hierarchical to ensure uniqueness.  Note
            # that if no category was explicitly set, we use the ID.
            category = menu_spec.get('category', menu_spec['id'])
            if len(parent_category) > 1:
                category = '%s.%s' % (parent_category, category)
            self.category_map[category] = path

            # Add all sub-menus to the queue so they get created as well.
            for child_spec in menu_spec.get('sub-menus', []):
                queue.append((child_spec, path, category))

        # Now create all the requested shortcuts.
        for shortcut in shortcuts:

            # Ensure the shortcut ends up in each of the requested categories.
            for mapped_category in shortcut['categories']:

                #print '=======', shortcut
                # Install the actual item
                self._install_shortcut(mapped_category, shortcut)


    def _install_shortcut(self, mapped_category, shortcut):
        # Separate the arguments to the invoked command from the command
        # itself.
        cmd_list = shortcut['cmd']
        cmd = cmd_list[0]
        if len(cmd_list) > 1:
            args = cmd_list[1:]
        else:
            args = []

        # Handle the special '{{FILEBROWSER}}' command by stripping it
        # out since File Explorer will automatically be launched when a
        # folder link is separated.
        if cmd == '{{FILEBROWSER}}':
            cmd = args[0]
            if len(args) > 1:
                args = args[1:]
            else:
                args = []

        # Otherwise, handle the special '{{WEBBROWSER}}' command by
        # invoking the Python standard lib's 'webbrowser' script.  This
        # allows us to specify that the url(s) should be opened in new
        # tabs.
        #
        # If this doesn't work, see the following website for details of
        # the special URL shortcut file format.  While split across two
        # lines it is one URL:
        #   http://delphi.about.com/gi/dynamic/offsite.htm?site= \
        #        http://www.cyanwerks.com/file-format-url.html
        elif cmd == '{{WEBBROWSER}}':
            cmd = join(sys.prefix, 'python.exe')
            import webbrowser
            args = [webbrowser.__file__, '-t'] + args

        # Now create the actual Windows shortcut.  Note that the API to
        # create a windows shortcut requires that a path to the icon
        # file be in a weird place -- second in a variable length
        # list of args.
        link = shortcut['name'] + '.lnk'
        comment = shortcut['comment']
        icon = shortcut.get('icon', None)
        if icon:
            shortcut_args = ['', icon]
        else:
            shortcut_args = []

        dst_dirs = [self.category_map[mapped_category]]  # Menu link

        if shortcut.get('desktop', None) and self.addtodesktop:
            dst_dirs.append(self.desktop_dir)            # Desktop link

        if shortcut.get('quicklaunch', None) and self.addtolauncher:
            dst_dirs.append(self.quicklaunch_dir)        # Quicklaunch link

        for dst_dir in dst_dirs:
            dst = join(dst_dir, link)
            if self._uninstall:
                try:
                    os.unlink(dst)
                    print "Removed: %r" % dst
                except:
                    print "Could not remove: %r" % dst
            else:
                wininst.create_shortcut(
                    quoted(cmd),
                    comment,
                    dst,
                    # the arguments of the command
                    ' '.join(quoted(arg) for arg in args),
                    *shortcut_args)


    def _uninstall_application_menus(self, menus, shortcuts, start_menu):
        # Keep track of the shortcut names, as the shortcuts we specify are the
        # only things we want to delete. Append '.lnk' to the name because
        # that's how they were created during install.
        shortcut_names = []
        for shortcut in shortcuts:
            name = shortcut['name'] + '.lnk'
            shortcut_names.append(name)

            # Since the _get_install_type() function does not work properly
            # during the uninstall process, we try to remove the desktop icon
            # from both the all-users and current user's desktop directory
            if shortcut.get('desktop', None):
                pth = join(common._get_all_users_desktop_directory(), name)
                try:
                    os.unlink(pth)
                except:
                    pass
                pth = join(common._get_current_user_desktop_directory(), name)
                try:
                    os.unlink(pth)
                except:
                    pass

            # Remove the quicklaunch icon if it was added
            if shortcut.get('quicklaunch', None) and self.addtolauncher:
                pth = join(self.quicklaunch_dir, name)
                try:
                    os.unlink(pth)
                except:
                    pass

        for top_menu in menus:
            top_name = top_menu['name']
            top_path = join(start_menu, top_name)

            # Keep track of possible menu directories to be deleted
            menu_paths = [top_path]

            for root, dirs, files in os.walk(top_path):
                for file in files:
                    if file in shortcut_names:
                        file_path = join(root, file)
                        os.remove(file_path)
                        print "Removed %s" % file_path
                for d in dirs:
                    # Prepend paths so that when we try to delete menu
                    # directories we start at the bottom-most directory
                    menu_paths.insert(0, join(root, d))

            # Delete menu directories. This should start from the bottom-most
            # directory and work its way up to the top-most. Only directories
            # that have been emptied will be deleted.
            # FIXME: This will also delete directories that already are empty
            # (not necessarily ones that we created), but that may be a
            # non-issue.
            for menu_path in menu_paths:
                if exists(menu_path):
                    try:
                        os.rmdir(menu_path)
                        print "Removed %s" % menu_path
                    except:
                        print "%s not empty, skipping." % menu_path
                        continue
                else:
                    print "%s does not exist, skipping." % menu_path