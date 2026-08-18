# -*- coding: utf-8 -*-
"""
ProfileManager - VERSÃO CORRIGIDA v2.1
Fixes: race condition Android TV, Window property timing, Container.Refresh único,
       should_show_profile_selector sem load_profiles() prematuro,
       switch_profile sem Refresh interno, delays ajustados para TCL P8M.
"""

import xbmc
import os
import json
import xbmcgui
import xbmcaddon
import xbmcvfs
import hashlib
import time
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _safe_sleep(ms):
    """Wrapper em torno de xbmc.sleep que aceita valores inteiros."""
    xbmc.sleep(int(ms))


def _set_profile_window_props(profile):
    """
    Escreve todas as Window(10000) properties de uma vez.
    Centralizar aqui evita esquecer alguma propriedade em qualquer ponto do código.
    """
    win = xbmcgui.Window(10000)
    win.setProperty('cineroom_active_profile_id',   profile['id'])
    win.setProperty('cineroom_active_profile_name', profile.get('name', ''))
    win.setProperty('cineroom_is_kids',             '1' if profile.get('is_kids') else '0')
    win.setProperty('cineroom_profile_role',        profile.get('role', 'adult'))


def _clear_profile_window_props():
    """Limpa todas as Window properties de perfil."""
    win = xbmcgui.Window(10000)
    for prop in (
        'cineroom_active_profile_id',
        'cineroom_active_profile_name',
        'cineroom_is_kids',
        'cineroom_profile_role',
    ):
        win.clearProperty(prop)


# ---------------------------------------------------------------------------
# AvatarPickerDialog
# ---------------------------------------------------------------------------

class AvatarPickerDialog(xbmcgui.WindowXMLDialog):
    """
    Wall de avatares em grid. Abre SelectAvatar.xml.
    Retorna o caminho relativo do avatar escolhido em self.selected,
    ou None se o usuário cancelou.

    IDs:
        50  — panel (grid de avatares)
        70  — botão Cancelar
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.avatars  = kwargs.get('avatars', [])
        self.is_kids  = kwargs.get('is_kids', False)
        self.selected = None

    def onInit(self):
        subtitle = 'Perfil infantil' if self.is_kids else 'Perfil adulto'
        try:
            xbmc.executebuiltin(f'Skin.SetString(AvatarSubtitle,{subtitle})')
        except Exception:
            pass

        panel = self.getControl(50)
        panel.reset()

        addon_path = xbmcaddon.Addon().getAddonInfo('path')

        for rel_path in self.avatars:
            full_path = os.path.join(addon_path, 'resources', 'medias', rel_path)
            name = os.path.splitext(os.path.basename(rel_path))[0].replace('avatar', '')
            li = xbmcgui.ListItem(label=name)
            li.setArt({'icon': full_path, 'thumb': full_path})
            panel.addItem(li)

        self.setFocusId(50)

    def onClick(self, control_id):
        if control_id == 50:
            panel = self.getControl(50)
            idx   = panel.getSelectedPosition()
            if 0 <= idx < len(self.avatars):
                self.selected = self.avatars[idx]
            self.close()
        elif control_id == 70:
            self.selected = None
            self.close()

    def onAction(self, action):
        if action.getId() in (
            xbmcgui.ACTION_PREVIOUS_MENU,
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_STOP,
        ):
            self.selected = None
            self.close()


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------

class ProfileManager:
    VERSION = "2.1"

    def __init__(self):
        self.addon        = xbmcaddon.Addon()
        self.addon_path   = xbmcvfs.translatePath(self.addon.getAddonInfo('path'))
        self.profile_path = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        self.profiles_file = os.path.join(self.profile_path, 'profiles.json')

        if not xbmcvfs.exists(self.profile_path):
            xbmcvfs.mkdirs(self.profile_path)

        self.current_profile = None
        self.load_profiles()
        self._migrate_profiles()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def load_profiles(self):
        """Carrega perfis do arquivo JSON."""
        if xbmcvfs.exists(self.profiles_file):
            try:
                with open(self.profiles_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                xbmc.log(f'[ProfileManager] Erro ao carregar profiles.json: {e}', xbmc.LOGERROR)
                self.data = self._create_default_structure()
        else:
            self.data = self._create_default_structure()
            self.save_profiles()

    def _create_default_structure(self):
        return {
            "version": self.VERSION,
            "profiles": [],
            "current_profile": None,
            "require_profile_selection": True,
            "next_profile_id": 1
        }

    def save_profiles(self):
        """
        Salva perfis com fsync para garantir persistência no Android.
        Em Android TV com armazenamento eMMC lento, o fsync é crítico.
        """
        try:
            with open(self.profiles_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            xbmc.log(f'[ProfileManager] Erro ao salvar profiles.json: {e}', xbmc.LOGERROR)

    # ------------------------------------------------------------------
    # Migração
    # ------------------------------------------------------------------

    def _migrate_profiles(self):
        """Migra perfis antigos para nova versão sem perder dados."""
        if self.data.get('version') == self.VERSION:
            return

        for profile in self.data.get('profiles', []):
            if 'parental_controls' not in profile:
                profile['parental_controls'] = {
                    'allow_uncertified': False,
                    'daily_time_limit': None,
                    'restrict_download': profile.get('is_kids', False),
                    'block_purchases': profile.get('is_kids', False)
                }
            if 'content_whitelist'  not in profile: profile['content_whitelist']  = []
            if 'content_blacklist'  not in profile: profile['content_blacklist']  = []
            if 'viewing_history'    not in profile: profile['viewing_history']    = []
            if 'blocked_attempts'   not in profile: profile['blocked_attempts']   = []

            if 'preferences' in profile:
                prefs = profile['preferences']
                if 'age_range' not in prefs:
                    prefs['age_range'] = '7_10_anos' if profile.get('is_kids') else None
                if 'allow_uncertified' not in prefs:
                    prefs['allow_uncertified'] = not profile.get('is_kids', False)

            if 'role' not in profile:
                if profile.get('is_kids'):
                    profile['role'] = 'kids'
                else:
                    adult_profiles = [p for p in self.data['profiles'] if not p.get('is_kids')]
                    profile['role'] = 'admin' if len(adult_profiles) == 0 else 'adult'

        self.data['version'] = self.VERSION
        self.save_profiles()

    # ------------------------------------------------------------------
    # Utilitários de ID
    # ------------------------------------------------------------------

    def _generate_unique_profile_id(self):
        return f'profile_{int(time.time() * 1000)}'

    # ------------------------------------------------------------------
    # Getters básicos
    # ------------------------------------------------------------------

    def get_profiles(self):
        return self.data.get('profiles', [])

    def get_profile_by_id(self, profile_id):
        for profile in self.data.get('profiles', []):
            if profile['id'] == profile_id:
                return profile
        return None

    def get_current_profile(self):
        """
        Retorna o perfil ativo.
        Prioridade: objeto em memória → Window property → disco.
        """
        if self.current_profile:
            return self.current_profile

        # Tenta recuperar da Window property (sobrevive ao garbage collector)
        session_id = xbmcgui.Window(10000).getProperty('cineroom_active_profile_id')
        if session_id:
            profile = self.get_profile_by_id(session_id)
            if profile:
                self.current_profile = profile
                return profile

        # Último recurso: disco
        profile_id = self.data.get('current_profile')
        if profile_id:
            profile = self.get_profile_by_id(profile_id)
            if profile:
                self.current_profile = profile
                return profile

        return None

    # ------------------------------------------------------------------
    # SWITCH DE PERFIL — corrigido para Android TV
    # ------------------------------------------------------------------

    def switch_profile(self, profile, skip_pin=False):
        """
        Ativa um perfil.

        IMPORTANTE: este método NÃO chama Container.Refresh.
        O chamador é responsável por disparar o Refresh DEPOIS de
        receber o retorno, com o delay adequado para o hardware.
        Isso evita race conditions onde o router do addon é acionado
        antes das Window properties e do JSON estarem consolidados.
        """
        if not profile:
            return None

        if not skip_pin and profile.get('pin') and not self._verify_pin(profile):
            return None

        # 1. Atualiza objeto em memória PRIMEIRO
        profile['last_access'] = datetime.now().isoformat()
        self.current_profile   = profile
        self.data['current_profile'] = profile['id']

        # 2. Propaga para Window(10000) ANTES de qualquer I/O
        #    Qualquer código que rodar durante o save já verá o perfil correto
        _set_profile_window_props(profile)
        
        try:
            from resources.lib.favorites import invalidate_profile_cache
            invalidate_profile_cache()
        except Exception:
            pass

        # 3. Persiste no disco
        self.save_profiles()

        # 4. Notificação visual
        avatar_path = os.path.join(
            self.addon_path, 'resources', 'medias', profile.get('avatar', '')
        )
        xbmcgui.Dialog().notification(
            'Perfil Alterado',
            f'Bem-vindo, {profile["name"]}!',
            avatar_path,
            time=2000,
            sound=False
        )

        # 5. Delay para o hardware fraco consolidar o estado
        #    NÃO chama Container.Refresh — responsabilidade do chamador
        _safe_sleep(400)

        xbmc.log(
            f'[ProfileManager] switch_profile OK → {profile["name"]} ({profile["id"]})',
            xbmc.LOGINFO
        )

        return profile

    def _do_refresh(self, extra_delay_ms=0):
        """
        Dispara Container.Refresh de forma segura.
        Centralizar aqui garante que sempre haja um delay mínimo antes do refresh,
        evitando que o router leia estado desatualizado.
        """
        if extra_delay_ms > 0:
            _safe_sleep(extra_delay_ms)
        xbmc.executebuiltin('Container.Refresh')
        xbmc.log('[ProfileManager] Container.Refresh disparado', xbmc.LOGINFO)

    # ------------------------------------------------------------------
    # SELETOR DE PERFIL — corrigido
    # ------------------------------------------------------------------

    def should_show_profile_selector(self):
        session_id = xbmcgui.Window(10000).getProperty('cineroom_active_profile_id')
        if session_id:
            if self.current_profile and self.current_profile.get('id') == session_id:
                return False
            profile = self.get_profile_by_id(session_id)
            if not profile:
                _safe_sleep(300)
                self.load_profiles()
                profile = self.get_profile_by_id(session_id)
            if profile:
                self.current_profile = profile
                return False
            _clear_profile_window_props()

        self.load_profiles()

        remember = self.addon.getSettingBool('remember_profile')
        if remember:
            profile_id = self.data.get('current_profile')
            if profile_id:
                profile = self.get_profile_by_id(profile_id)
                if profile:
                    self.current_profile = profile
                    _set_profile_window_props(profile)
                    xbmc.log(
                        f'[ProfileManager] Perfil restaurado via remember: {profile["name"]}',
                        xbmc.LOGINFO
                    )
                    return False

        self.current_profile          = None
        self.data['current_profile']  = None
        return True

    def show_profile_selector(self):
        """
        Exibe o seletor de perfis (XML customizado com fallback nativo).
        Após confirmar o perfil, dispara Container.Refresh com delay seguro.
        """
        profiles = self.get_profiles()

        if not profiles:
            if xbmcgui.Dialog().yesno(
                'Bem-vindo!',
                'Nenhum perfil encontrado. Deseja criar um agora?'
            ):
                result = self.create_profile_wizard()
                if result:
                    self._do_refresh(extra_delay_ms=500)
                return result
            return None

        try:
            from resources.lib.dialog.dialog_select_profile import DialogSelectProfile

            dialog = DialogSelectProfile(
                "SelectProfile.xml",
                self.addon_path,
                "Default",
                "1080i",
                profiles=profiles,
                addon_path=self.addon_path
            )
            dialog.doModal()
            selected = dialog.get_selected_profile()
            del dialog

            # Pequeno respiro após fechar a janela modal no Android
            _safe_sleep(200)

            return self._handle_profile_selection(selected)

        except Exception as e:
            import traceback
            xbmc.log(
                f'[ProfileManager] show_profile_selector falhou, usando fallback: {e}\n'
                + traceback.format_exc(),
                xbmc.LOGERROR
            )
            return self._show_profile_selector_fallback()

    def _handle_profile_selection(self, selected):
        """
        Processa o resultado do seletor de perfis.
        Centralizado aqui para ser reutilizado pelo fallback.
        """
        if selected == '__ADD_NEW__':
            result = self.create_profile_wizard()
        elif selected == '__ADD_ADULT__':
            result = self.create_profile(is_kids=False)
        elif selected == '__ADD_KID__':
            result = self.create_profile(is_kids=True)
        elif selected == '__MANAGE__':
            self.manage_profiles()
            return self.get_current_profile()
        elif selected and isinstance(selected, dict):
            # Perfil existente — PIN já verificado pelo seletor XML,
            # mas no fallback pode chegar sem verificação prévia
            if selected.get('pin') and not self._verify_pin(selected):
                xbmcgui.Dialog().notification(
                    'Acesso Negado',
                    'PIN incorreto',
                    xbmcgui.NOTIFICATION_ERROR,
                    3000
                )
                return None
            result = self.switch_profile(selected, skip_pin=True)
        else:
            return None

        if result:
            # Refresh único, com delay adequado para Android TV
            self._do_refresh(extra_delay_ms=800)

        return result

    def _show_profile_selector_fallback(self):
        """
        Seletor fallback usando Dialog().select nativo.
        Usado quando o XML customizado falha (ex: primeiro boot, skin corrompida).
        """
        try:
            # Recarrega do disco para garantir lista atualizada
            self.load_profiles()
            profiles = self.get_profiles()

            items = []
            for profile in profiles:
                item = xbmcgui.ListItem(profile['name'])
                avatar_path = os.path.join(
                    self.addon_path,
                    'resources', 'medias',
                    profile.get('avatar', 'icons/trakt_menu.png')
                )
                item.setArt({'icon': avatar_path, 'thumb': avatar_path})
                if profile.get('last_access'):
                    try:
                        item.setLabel2(f"Último acesso: {profile['last_access'][:10]}")
                    except Exception:
                        pass
                items.append(item)

            add_item = xbmcgui.ListItem('[B]+ Adicionar Perfil[/B]')
            items.append(add_item)

            selected_idx = xbmcgui.Dialog().select(
                'Quem está assistindo?',
                items,
                useDetails=True
            )

            xbmc.log(
                f'[ProfileManager] Fallback: Dialog.select retornou índice {selected_idx}',
                xbmc.LOGINFO
            )

            if selected_idx < 0:
                xbmc.log('[ProfileManager] Fallback: seleção cancelada', xbmc.LOGINFO)
                return None

            # ⚠️ Delay crítico: janela modal precisa fechar completamente antes
            # de qualquer operação em hardware lento (TCL P8M / eMMC lento)
            _safe_sleep(400)

            # Usuário escolheu "Adicionar Perfil"
            if selected_idx == len(profiles):
                xbmc.log('[ProfileManager] Fallback: criando novo perfil', xbmc.LOGINFO)
                _safe_sleep(200)
                result = self.create_profile_wizard()
                if result:
                    _safe_sleep(400)
                    self._do_refresh(extra_delay_ms=300)
                return result

            # Revalida índice (lista pode ter mudado se create foi chamado antes)
            if selected_idx >= len(profiles):
                xbmc.log(
                    f'[ProfileManager] Fallback: índice inválido {selected_idx} '
                    f'(total={len(profiles)})',
                    xbmc.LOGWARNING
                )
                return None

            # Recarrega do disco antes da troca para evitar estado stale
            self.load_profiles()
            fresh_profiles = self.get_profiles()

            if selected_idx >= len(fresh_profiles):
                xbmc.log(
                    f'[ProfileManager] Fallback: índice inválido após reload '
                    f'{selected_idx} (total={len(fresh_profiles)})',
                    xbmc.LOGWARNING
                )
                return None

            selected_profile = fresh_profiles[selected_idx]

            xbmc.log(
                f'[ProfileManager] Fallback: perfil selecionado → '
                f'{selected_profile.get("name")} ({selected_profile.get("id")})',
                xbmc.LOGINFO
            )

            # Verifica PIN antes de trocar
            if selected_profile.get('pin') and not self._verify_pin(selected_profile):
                xbmcgui.Dialog().notification(
                    'Acesso Negado',
                    'PIN incorreto',
                    xbmcgui.NOTIFICATION_ERROR,
                    3000
                )
                return None

            _safe_sleep(300)
            result = self.switch_profile(selected_profile, skip_pin=True)

            if result:
                # Delay maior no fallback — Android TV com eMMC lento
                self._do_refresh(extra_delay_ms=600)
                xbmc.log(
                    f'[ProfileManager] Fallback: perfil aplicado com sucesso → '
                    f'{result.get("name")}',
                    xbmc.LOGINFO
                )
            else:
                xbmc.log(
                    '[ProfileManager] Fallback: switch_profile retornou None',
                    xbmc.LOGWARNING
                )

            return result

        except Exception as e:
            xbmc.log(
                f'[ProfileManager] Erro em _show_profile_selector_fallback: {e}',
                xbmc.LOGERROR
            )
            return None

    # ------------------------------------------------------------------
    # LOGOUT
    # ------------------------------------------------------------------

    def logout_profile(self):
        """Encerra a sessão do perfil atual."""
        if self.current_profile:
            xbmc.log(
                f'[ProfileManager] Logout: {self.current_profile.get("name")}',
                xbmc.LOGINFO
            )

        self.current_profile         = None
        self.data['current_profile'] = None
        self.save_profiles()
        _clear_profile_window_props()
        
        try:
            from resources.lib.favorites import invalidate_profile_cache
            invalidate_profile_cache()
        except Exception:
            pass

    def switch_to_another_profile(self):
        """
        Faz logout e abre o seletor de perfis.
        NÃO chama Container.Refresh extra — show_profile_selector já cuida disso.
        """
        self.logout_profile()
        return self.show_profile_selector()

    # ------------------------------------------------------------------
    # CRIAÇÃO DE PERFIL
    # ------------------------------------------------------------------

    def create_profile_wizard(self):
        """Wizard completo de criação de perfil."""
        dialog = xbmcgui.Dialog()

        name = dialog.input('Nome do Perfil', type=xbmcgui.INPUT_ALPHANUM)
        if not name:
            return None

        profile_types = ['Adulto', 'Infantil']
        profile_type  = dialog.select('Tipo de Perfil', profile_types)
        if profile_type < 0:
            return None

        is_kids = (profile_type == 1)

        age_range = None
        if is_kids:
            age_options = [
                '2-6 anos (crianças pequenas)',
                '7-10 anos (crianças)',
                '11-14 anos (pré-adolescentes)',
                'Livre (todas idades)'
            ]
            age_idx   = dialog.select('Faixa Etária Permitida', age_options)
            age_map   = {0: '2_6_anos', 1: '7_10_anos', 2: '11_14_anos', 3: 'livre'}
            age_range = age_map.get(age_idx, '7_10_anos')

        avatar = self.select_avatar(is_kids)
        if not avatar:
            avatar = 'icons/tv.png' if is_kids else 'icons/trakt_menu.png'

        pin = ""
        if dialog.yesno('Proteção por PIN', 'Deseja proteger este perfil com PIN?'):
            pin_input = dialog.numeric(0, 'Digite o PIN (4 dígitos)')
            if pin_input and len(pin_input) == 4:
                pin = hashlib.sha256(pin_input.encode()).hexdigest()
            else:
                dialog.ok('Aviso', 'PIN deve ter 4 dígitos. Perfil criado sem proteção.')

        parental_controls = None
        if is_kids:
            parental_controls = self._setup_parental_controls(dialog)

        trakt_data = self._wizard_trakt(dialog, is_kids)

        adult_profiles = [p for p in self.data['profiles'] if not p.get('is_kids')]
        if is_kids:
            role = 'kids'
        elif len(adult_profiles) == 0:
            role = 'admin'
        else:
            role = 'adult'

        new_profile = self._build_profile_dict(
            name=name,
            avatar=avatar,
            is_kids=is_kids,
            role=role,
            pin=pin,
            age_range=age_range,
            parental_controls=parental_controls,
            trakt_data=trakt_data
        )

        self.data['profiles'].append(new_profile)
        self.save_profiles()

        dialog.ok('Sucesso!', f'Perfil "{name}" criado com sucesso!')

        # switch_profile sem Refresh — o chamador (show_profile_selector) fará o Refresh
        return self.switch_profile(new_profile)

    def create_profile(self, is_kids=False):
        """
        Criação simplificada (chamada pelos botões ADULTO/KID no seletor).
        """
        dialog = xbmcgui.Dialog()

        profile_type = "Infantil" if is_kids else "Adulto"
        name = dialog.input(f'Nome do Perfil {profile_type}', type=xbmcgui.INPUT_ALPHANUM)
        if not name:
            return None

        avatar = self.select_avatar(is_kids)
        if not avatar:
            avatar = 'icons/tv.png' if is_kids else 'icons/trakt_menu.png'

        pin = ""
        if dialog.yesno('Proteção por PIN', f'Deseja proteger o perfil "{name}" com PIN?'):
            pin_input = dialog.numeric(0, 'Digite o PIN (4 dígitos)')
            if pin_input and len(pin_input) == 4:
                pin = hashlib.sha256(pin_input.encode()).hexdigest()
            else:
                dialog.ok('Aviso', 'PIN deve ter 4 dígitos. Perfil criado sem proteção.')

        age_range = None
        if is_kids:
            age_options = [
                '2-6 anos (crianças pequenas)',
                '7-10 anos (crianças)',
                '11-14 anos (pré-adolescentes)',
                'Livre (todas idades)'
            ]
            age_idx   = dialog.select('Faixa Etária Permitida', age_options)
            if age_idx < 0:
                age_idx = 1
            age_map   = {0: '2_6_anos', 1: '7_10_anos', 2: '11_14_anos', 3: 'livre'}
            age_range = age_map.get(age_idx, '7_10_anos')

        adult_profiles = [p for p in self.data['profiles'] if not p.get('is_kids')]
        if is_kids:
            role = 'kids'
        elif len(adult_profiles) == 0:
            role = 'admin'
        else:
            role = 'adult'

        trakt_data = self._wizard_trakt(dialog, is_kids)

        new_profile = self._build_profile_dict(
            name=name,
            avatar=avatar,
            is_kids=is_kids,
            role=role,
            pin=pin,
            age_range=age_range,
            parental_controls=None,
            trakt_data=trakt_data
        )

        self.data['profiles'].append(new_profile)
        self.save_profiles()

        notification_msg = f'Perfil "{name}" criado'
        if trakt_data and trakt_data.get('username'):
            notification_msg += f' · Trakt: {trakt_data["username"]}'

        dialog.notification(
            'Perfil Criado!',
            notification_msg,
            xbmcgui.NOTIFICATION_INFO,
            3000
        )

        return self.switch_profile(new_profile)

    def _build_profile_dict(self, name, avatar, is_kids, role, pin,
                            age_range, parental_controls, trakt_data):
        """Monta o dicionário de um perfil novo de forma padronizada."""
        return {
            'id':           self._generate_unique_profile_id(),
            'name':         name,
            'avatar':       avatar,
            'theme':        'kids' if is_kids else 'dark',
            'color_scheme': 'rainbow' if is_kids else 'blue',
            'layout':       'grid',
            'pin':          pin,
            'is_kids':      is_kids,
            'role':         role,
            'preferences': {
                'auto_play_next':     True,
                'skip_intro':         True,
                'preferred_quality':  '1080p',
                'subtitle_language':  'pt-br',
                'age_range':          age_range,
                'allow_uncertified':  not is_kids
            },
            'parental_controls': parental_controls or {
                'allow_uncertified': not is_kids,
                'daily_time_limit':  None,
                'restrict_download': is_kids,
                'block_purchases':   is_kids
            },
            'trakt':             trakt_data,
            'content_whitelist': [],
            'content_blacklist': [],
            'viewing_history':   [],
            'blocked_attempts':  [],
            'history':           [],
            'watchlist':         [],
            'continue_watching': [],
            'created_at':        datetime.now().isoformat(),
            'last_access':       datetime.now().isoformat()
        }

    def _wizard_trakt(self, dialog, is_kids):
        """
        Sub-fluxo de autenticação Trakt durante criação de perfil.
        Retorna dict com token/refresh/username ou None.
        """
        if is_kids:
            return None

        if not dialog.yesno('Integração Trakt', 'Deseja conectar com Trakt neste perfil?'):
            return None

        current_token    = self.addon.getSetting('trakt_access_token')
        current_refresh  = self.addon.getSetting('trakt_refresh_token')
        current_username = self.addon.getSetting('trakt_username')

        if current_token and current_username:
            # Já existe conta — pergunta se reutiliza ou autentica nova
            nova_conta = dialog.yesno(
                'Trakt Já Conectado',
                f'Conta ativa: [B]{current_username}[/B]\n\nUsar esta conta ou autenticar nova?',
                nolabel='Usar esta conta',
                yeslabel='Autenticar nova conta'
            )
            if nova_conta:
                try:
                    from resources.lib.trakt.trakt_sync import authenticate_trakt
                    authenticate_trakt()
                    current_token    = self.addon.getSetting('trakt_access_token')
                    current_refresh  = self.addon.getSetting('trakt_refresh_token')
                    current_username = self.addon.getSetting('trakt_username')
                except Exception as e:
                    xbmc.log(f'[ProfileManager] Erro Trakt auth: {e}', xbmc.LOGERROR)
                    dialog.ok('Erro', f'Falha ao autenticar no Trakt:\n{str(e)}')
        else:
            try:
                from resources.lib.trakt.trakt_sync import authenticate_trakt
                if authenticate_trakt():
                    current_token    = self.addon.getSetting('trakt_access_token')
                    current_refresh  = self.addon.getSetting('trakt_refresh_token')
                    current_username = self.addon.getSetting('trakt_username')
                else:
                    dialog.ok('Trakt', 'Autenticação cancelada. Perfil criado sem Trakt.')
                    return None
            except Exception as e:
                xbmc.log(f'[ProfileManager] Erro Trakt auth: {e}', xbmc.LOGERROR)
                dialog.ok('Erro', f'Falha ao autenticar no Trakt:\n{str(e)}')
                return None

        if current_token:
            return {
                'token':    current_token,
                'refresh':  current_refresh,
                'username': current_username
            }
        return None

    def _setup_parental_controls(self, dialog):
        """Configuração detalhada de controle parental."""
        controls = {
            'allow_uncertified': False,
            'daily_time_limit':  None,
            'restrict_download': True,
            'block_purchases':   True
        }

        controls['allow_uncertified'] = dialog.yesno(
            'Conteúdo Sem Classificação',
            'Permitir filmes/séries sem classificação etária?',
            nolabel='Não (mais seguro)',
            yeslabel='Sim'
        )

        if dialog.yesno('Limite de Tempo', 'Deseja configurar limite de tempo diário?'):
            hours = dialog.numeric(0, 'Máximo de horas por dia (1-8)')
            if hours and 1 <= int(hours) <= 8:
                controls['daily_time_limit'] = int(hours) * 60

        return controls

    # ------------------------------------------------------------------
    # PIN
    # ------------------------------------------------------------------

    def _verify_pin(self, profile):
        """Verifica PIN com até 3 tentativas."""
        if not profile.get('pin'):
            return True

        max_attempts = 3
        for attempt in range(max_attempts):
            remaining = max_attempts - attempt
            prompt    = f"PIN para {profile['name']}"
            if attempt > 0:
                prompt += f' ({remaining} tentativa(s) restante(s))'

            pin_input = xbmcgui.Dialog().numeric(0, prompt)
            if not pin_input:
                return False

            if hashlib.sha256(pin_input.encode()).hexdigest() == profile['pin']:
                return True

            if attempt < max_attempts - 1:
                xbmcgui.Dialog().notification(
                    'PIN Incorreto',
                    f'{remaining - 1} tentativa(s) restante(s)',
                    xbmcgui.NOTIFICATION_WARNING,
                    2000
                )

        return False

    # ------------------------------------------------------------------
    # WHITELIST / BLACKLIST
    # ------------------------------------------------------------------

    def add_to_profile_blacklist(self, profile_id, tmdb_id, title, media_type='movie'):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return False
        if 'content_blacklist' not in profile:
            profile['content_blacklist'] = []
        if any(item['tmdb_id'] == tmdb_id for item in profile['content_blacklist']):
            xbmcgui.Dialog().notification('Já Bloqueado', f'{title} já está bloqueado', time=2000)
            return False
        profile['content_blacklist'].append({
            'tmdb_id':    tmdb_id,
            'title':      title,
            'media_type': media_type,
            'blocked_at': datetime.now().isoformat()
        })
        self.save_profiles()
        xbmcgui.Dialog().notification(
            'Conteúdo Bloqueado',
            f'{title} bloqueado para {profile["name"]}',
            time=2000
        )
        return True

    def add_to_profile_whitelist(self, profile_id, tmdb_id, title, media_type='movie'):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return False
        if 'content_whitelist' not in profile:
            profile['content_whitelist'] = []
        if any(item['tmdb_id'] == tmdb_id for item in profile['content_whitelist']):
            xbmcgui.Dialog().notification('Já Permitido', f'{title} já está permitido', time=2000)
            return False
        profile['content_whitelist'].append({
            'tmdb_id':    tmdb_id,
            'title':      title,
            'media_type': media_type,
            'allowed_at': datetime.now().isoformat()
        })
        self.save_profiles()
        xbmcgui.Dialog().notification(
            'Conteúdo Permitido',
            f'{title} permitido para {profile["name"]}',
            time=2000
        )
        return True

    def remove_from_blacklist(self, profile_id, tmdb_id):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return False
        profile['content_blacklist'] = [
            i for i in profile.get('content_blacklist', []) if i['tmdb_id'] != tmdb_id
        ]
        self.save_profiles()
        return True

    def remove_from_whitelist(self, profile_id, tmdb_id):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return False
        profile['content_whitelist'] = [
            i for i in profile.get('content_whitelist', []) if i['tmdb_id'] != tmdb_id
        ]
        self.save_profiles()
        return True

    # ------------------------------------------------------------------
    # HISTÓRICO E MONITORAMENTO
    # ------------------------------------------------------------------

    def track_viewing(self, profile_id, item_info):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return
        viewing = {
            'title':     item_info.get('title', 'Unknown'),
            'tmdb_id':   item_info.get('tmdb_id'),
            'type':      item_info.get('type', 'unknown'),
            'duration':  item_info.get('duration', 0),
            'timestamp': datetime.now().isoformat(),
            'rating':    item_info.get('certification', 'NR')
        }
        if 'viewing_history' not in profile:
            profile['viewing_history'] = []
        profile['viewing_history'].append(viewing)
        if len(profile['viewing_history']) > 100:
            profile['viewing_history'] = profile['viewing_history'][-100:]
        self.save_profiles()

    def log_blocked_attempt(self, profile_id, item_info):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return
        if 'blocked_attempts' not in profile:
            profile['blocked_attempts'] = []
        profile['blocked_attempts'].append({
            'title':     item_info.get('title', 'Unknown'),
            'tmdb_id':   item_info.get('tmdb_id'),
            'rating':    item_info.get('certification', 'NR'),
            'reason':    item_info.get('block_reason', 'Filtro de conteúdo'),
            'timestamp': datetime.now().isoformat()
        })
        if len(profile['blocked_attempts']) > 50:
            profile['blocked_attempts'] = profile['blocked_attempts'][-50:]
        self.save_profiles()

    def get_viewing_report(self, profile_id, days=7):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return None
        history = profile.get('viewing_history', [])
        cutoff  = datetime.now() - timedelta(days=days)
        recent  = [h for h in history if datetime.fromisoformat(h['timestamp']) > cutoff]
        total_time = sum(h.get('duration', 0) for h in recent)
        by_type    = {}
        for item in recent:
            t = item.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
        return {
            'profile_name':          profile['name'],
            'period_days':           days,
            'total_items':           len(recent),
            'total_minutes':         total_time,
            'total_hours':           round(total_time / 60, 1),
            'daily_average_minutes': round(total_time / days, 1) if days > 0 else 0,
            'by_type':               by_type,
            'blocked_attempts':      len(profile.get('blocked_attempts', []))
        }

    def show_viewing_report(self, profile_id):
        report = self.get_viewing_report(profile_id, days=7)
        if not report:
            xbmcgui.Dialog().ok('Erro', 'Não foi possível gerar o relatório.')
            return
        text = (
            f"Relatório de {report['profile_name']}\n"
            f"Período: Últimos {report['period_days']} dias\n\n"
            f"Total assistido: {report['total_items']} itens\n"
            f"Tempo total: {report['total_hours']} horas\n"
            f"Média diária: {report['daily_average_minutes']} minutos\n\n"
            f"Por tipo:\n"
        )
        for media_type, count in report['by_type'].items():
            text += f"  • {media_type}: {count}\n"
        if report['blocked_attempts'] > 0:
            text += f"\n⚠️ Tentativas bloqueadas: {report['blocked_attempts']}"
        xbmcgui.Dialog().textviewer('Relatório de Visualização', text)

    # ------------------------------------------------------------------
    # CONTROLE DE TEMPO
    # ------------------------------------------------------------------

    def check_time_limit(self, profile_id):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return True
        limit = profile.get('parental_controls', {}).get('daily_time_limit')
        if not limit:
            return True
        today        = datetime.now().date()
        history      = profile.get('viewing_history', [])
        today_viewing = [
            h for h in history
            if datetime.fromisoformat(h['timestamp']).date() == today
        ]
        total_today = sum(h.get('duration', 0) for h in today_viewing)
        if total_today >= limit:
            remaining   = max(0, limit - total_today)
            hours_limit = limit // 60
            xbmcgui.Dialog().ok(
                'Limite de Tempo Atingido',
                f'Limite diário de {hours_limit}h atingido.\n'
                f'Tempo restante hoje: {remaining} minutos'
            )
            return False
        return True

    def get_remaining_time_today(self, profile_id):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return None
        limit = profile.get('parental_controls', {}).get('daily_time_limit')
        if not limit:
            return None
        today        = datetime.now().date()
        history      = profile.get('viewing_history', [])
        today_viewing = [
            h for h in history
            if datetime.fromisoformat(h['timestamp']).date() == today
        ]
        total_today = sum(h.get('duration', 0) for h in today_viewing)
        return max(0, limit - total_today)

    # ------------------------------------------------------------------
    # AVATARES
    # ------------------------------------------------------------------

    def get_available_avatars(self, is_kids=False):
        avatars_dir = os.path.join(self.addon_path, 'resources', 'medias', 'avatars')
        if not os.path.exists(avatars_dir):
            return []
        avatars = []
        for f in os.listdir(avatars_dir):
            if f.lower().endswith(('.png', '.jpg')):
                avatars.append(os.path.join('avatars', f))
        return sorted(avatars)

    def select_avatar(self, is_kids=False):
        """Wall visual de avatares em grid (SelectAvatar.xml) com fallback blindado para Linux / LibreELEC."""
        avatars = self.get_available_avatars(is_kids)
        if not avatars:
            return None

        # Tentar abrir o diálogo XML nas possíveis variações de nomes e resoluções
        for xml_name in ['SelectAvatar.xml', 'Selectavatar.xml', 'selectavatar.xml']:
            for skin_folder in ['Default', 'default']:
                for res_folder in ['1080i', '1080p', '720p', '16x9', 'xml']:
                    try:
                        dialog = AvatarPickerDialog(
                            xml_name,
                            self.addon_path,
                            skin_folder,
                            res_folder,
                            avatars=avatars,
                            is_kids=is_kids,
                        )
                        dialog.doModal()
                        result = dialog.selected
                        del dialog
                        if result is not None:
                            return result
                    except Exception as e:
                        continue

        # Fallback garantido usando diálogo nativo caso o Kodi não carregue o XML na skin atual
        try:
            items = []
            for rel_path in avatars:
                full_path = os.path.join(self.addon_path, 'resources', 'medias', rel_path)
                name = os.path.splitext(os.path.basename(rel_path))[0].replace('avatar', 'Avatar ').strip()
                li = xbmcgui.ListItem(label=name)
                li.setArt({'icon': full_path, 'thumb': full_path})
                items.append(li)
            sel = xbmcgui.Dialog().select("Escolha o Avatar", items, useDetails=False)
            if sel >= 0:
                return avatars[sel]
        except Exception:
            pass

        return avatars[0] if avatars else 'avatars/avatar1.png'

    # ------------------------------------------------------------------
    # GERENCIAMENTO DE PERFIS
    # ------------------------------------------------------------------

    def manage_profiles(self):
        profiles = self.get_profiles()

        while True:
            items = []
            for profile in profiles:
                item = xbmcgui.ListItem(profile['name'])
                avatar_path = os.path.join(
                    self.addon_path, 'resources', 'medias',
                    profile.get('avatar', 'icons/trakt_menu.png')
                )
                item.setArt({'icon': avatar_path})
                items.append(item)
            items.append(xbmcgui.ListItem('[B]Voltar[/B]'))

            selected = xbmcgui.Dialog().select('Gerenciar Perfis', items, useDetails=True)

            if selected < 0 or selected == len(profiles):
                break

            profile = profiles[selected]
            actions = [
                'Editar Nome',
                'Alterar Avatar',
                'Alterar PIN',
                'Ver Relatório',
                'Gerenciar Bloqueios',
                'Excluir Perfil'
            ]
            action = xbmcgui.Dialog().select(f'Perfil: {profile["name"]}', actions)

            if action == 0:
                new_name = xbmcgui.Dialog().input('Novo Nome', profile['name'])
                if new_name:
                    profile['name'] = new_name
                    self.save_profiles()

            elif action == 1:
                new_avatar = self.select_avatar(profile.get('is_kids', False))
                if new_avatar:
                    profile['avatar'] = new_avatar
                    self.save_profiles()
                    xbmcgui.Dialog().notification(
                        'Avatar Atualizado',
                        f'Avatar de {profile["name"]} alterado com sucesso',
                        time=2000
                    )

            elif action == 2:
                if profile.get('pin'):
                    if xbmcgui.Dialog().yesno('Remover PIN', 'Deseja remover o PIN?'):
                        profile['pin'] = ""
                        self.save_profiles()
                else:
                    pin = xbmcgui.Dialog().numeric(0, 'Digite o PIN (4 dígitos)')
                    if pin and len(pin) == 4:
                        profile['pin'] = hashlib.sha256(pin.encode()).hexdigest()
                        self.save_profiles()

            elif action == 3:
                self.show_viewing_report(profile['id'])

            elif action == 4:
                self._manage_profile_lists(profile)

            elif action == 5:
                if len(profiles) == 1:
                    xbmcgui.Dialog().ok('Erro', 'Não é possível excluir o único perfil.')
                elif xbmcgui.Dialog().yesno('Excluir', f'Excluir "{profile["name"]}"?'):
                    self.data['profiles'].remove(profile)
                    if self.data['current_profile'] == profile['id']:
                        self.data['current_profile'] = None
                        self.current_profile         = None
                        _clear_profile_window_props()
                    self.save_profiles()
                    break

    def _manage_profile_lists(self, profile):
        options = ['Ver Bloqueados (Blacklist)', 'Ver Permitidos (Whitelist)', 'Voltar']
        choice  = xbmcgui.Dialog().select(f'Listas de {profile["name"]}', options)
        if choice == 0:
            self._show_content_list(profile, 'content_blacklist', 'Conteúdo Bloqueado')
        elif choice == 1:
            self._show_content_list(profile, 'content_whitelist', 'Conteúdo Permitido')

    def _show_content_list(self, profile, list_key, list_name):
        content_list = profile.get(list_key, [])
        if not content_list:
            xbmcgui.Dialog().ok(list_name, f'Nenhum item em {list_name.lower()}')
            return
        items = []
        for item in content_list:
            li = xbmcgui.ListItem(item['title'])
            li.setLabel2(
                f"{item['media_type']} - "
                f"{item.get('blocked_at', item.get('allowed_at', ''))[:10]}"
            )
            items.append(li)
        items.append(xbmcgui.ListItem('[B]Voltar[/B]'))
        selected = xbmcgui.Dialog().select(list_name, items, useDetails=True)
        if 0 <= selected < len(content_list):
            item = content_list[selected]
            if xbmcgui.Dialog().yesno('Remover', f'Remover "{item["title"]}" da lista?'):
                if list_key == 'content_blacklist':
                    self.remove_from_blacklist(profile['id'], item['tmdb_id'])
                else:
                    self.remove_from_whitelist(profile['id'], item['tmdb_id'])

    # ------------------------------------------------------------------
    # ESTATÍSTICAS
    # ------------------------------------------------------------------

    def get_profile_stats(self, profile_id):
        profile = self.get_profile_by_id(profile_id)
        if not profile:
            return None
        history       = profile.get('viewing_history', [])
        total_minutes = sum(h.get('duration', 0) for h in history)
        by_type       = {}
        for item in history:
            t = item.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
        week_ago = datetime.now() - timedelta(days=7)
        recent   = [h for h in history if datetime.fromisoformat(h['timestamp']) > week_ago]
        return {
            'name':                 profile['name'],
            'created_at':           profile.get('created_at', 'Desconhecido'),
            'last_access':          profile.get('last_access', 'Nunca'),
            'total_items_watched':  len(history),
            'total_hours':          round(total_minutes / 60, 1),
            'items_this_week':      len(recent),
            'by_type':              by_type,
            'whitelist_count':      len(profile.get('content_whitelist', [])),
            'blacklist_count':      len(profile.get('content_blacklist', [])),
            'blocked_attempts':     len(profile.get('blocked_attempts', []))
        }

    def show_profile_stats(self, profile_id):
        stats = self.get_profile_stats(profile_id)
        if not stats:
            xbmcgui.Dialog().ok('Erro', 'Perfil não encontrado')
            return
        text = (
            f"Perfil: {stats['name']}\n"
            f"Criado em: {stats['created_at'][:10]}\n"
            f"Último acesso: {stats['last_access'][:10]}\n\n"
            f"📊 ESTATÍSTICAS:\n"
            f"Total assistido: {stats['total_items_watched']} itens\n"
            f"Tempo total: {stats['total_hours']} horas\n"
            f"Esta semana: {stats['items_this_week']} itens\n\n"
        )
        if stats['by_type']:
            text += 'Por tipo:\n'
            for media_type, count in stats['by_type'].items():
                text += f'  • {media_type}: {count}\n'
            text += '\n'
        text += (
            f"🔒 CONTROLE:\n"
            f"Whitelist: {stats['whitelist_count']} itens\n"
            f"Blacklist: {stats['blacklist_count']} itens\n"
        )
        if stats['blocked_attempts'] > 0:
            text += f"⚠️ Tentativas bloqueadas: {stats['blocked_attempts']}\n"
        xbmcgui.Dialog().textviewer(f'Estatísticas - {stats["name"]}', text)

    # ------------------------------------------------------------------
    # MENU DE ADMINISTRAÇÃO
    # ------------------------------------------------------------------

    def admin_menu(self):
        while True:
            options = [
                'Gerenciar Perfis',
                'Ver Estatísticas',
                'Fazer Backup',
                'Restaurar Backup',
                'Validar Perfis',
                'Limpar Convidados Expirados',
                'Voltar'
            ]
            choice = xbmcgui.Dialog().select('Administração de Perfis', options)

            if choice == 0:
                self.manage_profiles()
            elif choice == 1:
                profiles      = self.get_profiles()
                profile_names = [p['name'] for p in profiles] + ['Voltar']
                sel = xbmcgui.Dialog().select('Escolha o Perfil', profile_names)
                if 0 <= sel < len(profiles):
                    self.show_profile_stats(profiles[sel]['id'])
            elif choice == 2:
                self.export_profiles()
            elif choice == 3:
                xbmcgui.Dialog().ok(
                    'Restaurar',
                    'Coloque o arquivo profiles_backup_*.json no diretório:\n\n'
                    f'{self.profile_path}'
                )
            elif choice == 4:
                count = self.validate_profiles()
                xbmcgui.Dialog().ok('Validação', f'{count} perfis válidos encontrados')
            elif choice == 5:
                removed = self.cleanup_expired_guests()
                xbmcgui.Dialog().ok('Limpeza', f'{removed} perfis convidados removidos')
            else:
                break

    # ------------------------------------------------------------------
    # BACKUP / RESTAURAÇÃO
    # ------------------------------------------------------------------

    def export_profiles(self, export_path=None):
        if not export_path:
            export_path = os.path.join(
                self.profile_path,
                f'profiles_backup_{int(time.time())}.json'
            )
        backup = {
            'version':     self.VERSION,
            'exported_at': datetime.now().isoformat(),
            'data':        self.data
        }
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(backup, f, indent=4, ensure_ascii=False)
            xbmcgui.Dialog().ok('Backup Criado', f'Perfis exportados!\n\n{export_path}')
            return True
        except Exception as e:
            xbmc.log(f'[ProfileManager] Erro ao exportar: {e}', xbmc.LOGERROR)
            xbmcgui.Dialog().ok('Erro', f'Falha ao exportar perfis:\n{str(e)}')
            return False

    def import_profiles(self, import_path):
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                backup = json.load(f)
            if backup.get('version') != self.VERSION:
                if not xbmcgui.Dialog().yesno(
                    'Versão Diferente',
                    f'Backup é versão {backup.get("version")}, atual é {self.VERSION}.\n'
                    'Continuar mesmo assim?'
                ):
                    return False
            if xbmcgui.Dialog().yesno(
                'Restaurar Perfis',
                'Isso sobrescreverá todos os perfis atuais.\n\nDeseja continuar?',
                nolabel='Cancelar',
                yeslabel='Restaurar'
            ):
                self.export_profiles(
                    os.path.join(
                        self.profile_path,
                        f'profiles_before_restore_{int(time.time())}.json'
                    )
                )
                self.data            = backup['data']
                self.current_profile = None
                self.save_profiles()
                xbmcgui.Dialog().ok(
                    'Restauração Concluída',
                    'Perfis restaurados com sucesso!\n\n'
                    'Um backup dos perfis anteriores foi criado.'
                )
                return True
            return False
        except Exception as e:
            xbmc.log(f'[ProfileManager] Erro ao importar: {e}', xbmc.LOGERROR)
            xbmcgui.Dialog().ok('Erro', f'Falha ao importar perfis:\n{str(e)}')
            return False

    # ------------------------------------------------------------------
    # UTILITÁRIOS
    # ------------------------------------------------------------------

    def has_active_profile(self):
        return self.current_profile is not None

    def validate_profiles(self):
        profiles   = self.data.get('profiles', [])
        seen_ids   = set()
        valid      = []
        for profile in profiles:
            pid = profile.get('id')
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                valid.append(profile)
        if len(valid) != len(profiles):
            self.data['profiles'] = valid
            self.save_profiles()
        return len(valid)

    def cleanup_expired_guests(self):
        now            = datetime.now()
        original_count = len(self.data.get('profiles', []))
        self.data['profiles'] = [
            p for p in self.data.get('profiles', [])
            if not (
                p.get('is_guest') and
                'expires_at' in p and
                datetime.fromisoformat(p['expires_at']) < now
            )
        ]
        removed = original_count - len(self.data['profiles'])
        if removed > 0:
            self.save_profiles()
        return removed

    def create_guest_profile(self):
        guest = {
            'id':       f'guest_{int(time.time())}',
            'name':     'Convidado',
            'avatar':   'icons/guest.png',
            'is_guest': True,
            'is_kids':  False,
            'role':     'adult',
            'preferences': {
                'auto_play_next':    True,
                'age_range':         '14_anos',
                'allow_uncertified': True
            },
            'parental_controls': {
                'allow_uncertified': True,
                'daily_time_limit':  None,
                'restrict_download': False,
                'block_purchases':   True
            },
            'content_whitelist': [],
            'content_blacklist': [],
            'viewing_history':   [],
            'blocked_attempts':  [],
            'created_at':        datetime.now().isoformat(),
            'expires_at':        (datetime.now() + timedelta(hours=24)).isoformat()
        }
        self.current_profile = guest
        xbmcgui.Dialog().notification(
            'Perfil Convidado',
            'Perfil temporário criado (expira em 24h)',
            time=3000
        )
        return guest

    # ------------------------------------------------------------------
    # COMPATIBILIDADE (métodos originais mantidos)
    # ------------------------------------------------------------------

    def get_profile_name(self):
        return self.current_profile['name'] if self.current_profile else 'Sem Perfil'

    def is_kids_profile(self):
        return self.current_profile.get('is_kids', False) if self.current_profile else False

    def is_admin_profile(self):
        return (
            self.current_profile.get('role') == 'admin'
            if self.current_profile else False
        )

    def can_manage_profiles(self):
        return (
            self.current_profile.get('role') in ('admin', 'adult')
            if self.current_profile else False
        )

    def get_profile_indicator(self):
        if self.current_profile:
            emoji = '👶' if self.current_profile.get('is_kids') else '👤'
            return f'{emoji} {self.current_profile["name"]}'
        return '❓ Sem Perfil'