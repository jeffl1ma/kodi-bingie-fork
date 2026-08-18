# -*- coding: utf-8 -*-
"""
Dialog personalizado para seleção de perfis - ESTILO HBO MAX
Versão 2.1 - CORREÇÃO: Botão Gerenciar Perfis
"""

import xbmcgui
import xbmc
import os


class DialogSelectProfile(xbmcgui.WindowXMLDialog):
    """
    Dialog personalizado para seleção de perfis (estilo HBO Max)
    """
    
    # IDs dos controles
    LIST_PROFILES = 50
    BTN_ADD_ADULT = 101
    BTN_ADD_KID = 102
    BTN_MANAGE = 103  # ← Constante explícita para clareza
    
    # Cores das bordas (atribuídas ciclicamente aos perfis)
    BORDER_COLORS = [
        "FFaa4de5",  # Roxo
        "FF4d9ae5",  # Azul
        "FFe54d9a",  # Rosa
        "FF5de5aa",  # Verde
        "FFe5aa4d",  # Laranja
    ]
    
    def __init__(self, *args, **kwargs):
        super(DialogSelectProfile, self).__init__()
        self.profiles = kwargs.get('profiles', [])
        self.addon_path = kwargs.get('addon_path', '')
        self.selected_profile = None
        
        for i, p in enumerate(self.profiles):
            pass
    
    def onInit(self):
        """Inicialização do dialog"""
        
        # Preencher a lista com os perfis
        self._populate_profiles()
        
        # Definir foco inicial
        try:
            self.setFocusId(self.LIST_PROFILES)
        except Exception as e:
            xbmc.log(f"[DialogSelectProfile] Erro ao definir foco: {e}", xbmc.LOGERROR)
    
    def _populate_profiles(self):
        """Preenche a lista com os perfis disponíveis"""
        try:
            list_control = self.getControl(self.LIST_PROFILES)
            list_control.reset()
            
            
            # Adicionar perfis existentes
            for idx, profile in enumerate(self.profiles):
                item = xbmcgui.ListItem(profile['name'])
                
                # Definir avatar
                avatar_path = self._get_avatar_path(profile)
                item.setArt({'icon': avatar_path, 'thumb': avatar_path})
                
                # Info adicional
                if profile.get('last_access'):
                    last_access = profile['last_access'][:10]
                    item.setLabel2(f"Último acesso: {last_access}")
                
                # Atribuir cor de borda única (ciclicamente)
                color_index = idx % len(self.BORDER_COLORS)
                item.setProperty('border_color', self.BORDER_COLORS[color_index])

                # Marcar se perfil tem PIN
                if profile.get('pin'):
                    item.setProperty('has_pin', 'true')
                    
                # Marcar se é perfil Kids (para exibir cadeado)
                if profile.get('is_kids'):
                    item.setProperty('is_kids', 'true')
                    
                # ── Estatísticas reais via history_db ──────────────────────
                try:
                    from resources.lib.db.history_db import history_db
                    from resources.lib.profile_stats import get_profile_stats

                    pid   = profile.get('id')
                    stats = get_profile_stats(pid) if pid else None

                    if stats:
                        fmt = stats['formatted']

                        # Barra de progresso: baseada em minutos assistidos
                        # Referência máxima = 3000 min (~50h) → 200px
                        total_min   = stats['watch_time'].get('total_minutes', 0)
                        progress_px = min(int((total_min / 3000) * 200), 200)
                        if progress_px > 0:
                            item.setProperty('watch_progress', str(progress_px))

                        # Stats textuais para o item focado no XML
                        item.setProperty('stat_time',      fmt['watch_time'])
                        item.setProperty('stat_completed', fmt['completed'])
                        item.setProperty('stat_streak',    fmt['streak'])
                        item.setProperty('stat_genres',    fmt['top_genres'])

                except Exception as _e:
                    pass

                # CRÍTICO: Armazenar ID do perfil e índice
                item.setProperty('profile_id', profile['id'])
                item.setProperty('profile_index', str(idx))
                
                list_control.addItem(item)
            
            
        except Exception as e:
            xbmc.log(f"[DialogSelectProfile] Erro ao popular lista: {e}", xbmc.LOGERROR)
            import traceback
            xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
    
    def _get_avatar_path(self, profile):
        """Retorna o caminho completo do avatar"""
        avatar = profile.get('avatar', 'icons/default_avatar.png')
        
        # Se já é um caminho absoluto, usa direto
        if os.path.isabs(avatar):
            return avatar
        
        # Senão, constrói o caminho relativo
        return os.path.join(
            self.addon_path,
            'resources', 'medias',
            avatar
        )
    
    def onClick(self, controlId):
        """Chamado quando um controle é clicado"""
        
        if controlId == self.LIST_PROFILES:
            self._handle_profile_selection()
        
        elif controlId == self.BTN_ADD_ADULT:
            self.selected_profile = '__ADD_ADULT__'
            self.close()
        
        elif controlId == self.BTN_ADD_KID:
            self.selected_profile = '__ADD_KID__'
            self.close()
            
        elif controlId == self.BTN_MANAGE:  # ID 103
            self.selected_profile = '__MANAGE__'
            self.close()
        
        else:
            pass
    
    def _handle_profile_selection(self):
        """Processa a seleção de um perfil existente"""
        try:
            list_control = self.getControl(self.LIST_PROFILES)
            selected_position = list_control.getSelectedPosition()
            
            
            # Pegar o item na posição selecionada
            selected_item = list_control.getSelectedItem()
            
            if not selected_item:
                xbmc.log("[DialogSelectProfile] ERRO: Item selecionado é None!", xbmc.LOGERROR)
                return
            
            profile_id = selected_item.getProperty('profile_id')
            profile_index = selected_item.getProperty('profile_index')
            
            
            # Buscar o perfil pelo ID (mais seguro que por índice)
            found = False
            for profile in self.profiles:
                if profile['id'] == profile_id:
                    self.selected_profile = profile
                    found = True
                    break
            
            if not found:
                pass
            
            self.close()
            
        except Exception as e:
            xbmc.log(f"[DialogSelectProfile] ERRO no _handle_profile_selection: {e}", xbmc.LOGERROR)
            import traceback
            xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
    
    def onAction(self, action):
        """Chamado quando uma ação é executada"""
        action_id = action.getId()
        
        # Log apenas para ações de navegação e seleção
        if action_id in (7, 1, 2, 3, 4):  # Select, Up, Down, Left, Right
            try:
                list_control = self.getControl(self.LIST_PROFILES)
                pos = list_control.getSelectedPosition()
            except:
                pass
        
        # Fechar o dialog com ESC ou Back
        if action_id in (9, 10, 92, 216, 247, 257, 275, 61467, 61448):
            self.selected_profile = None
            self.close()
    
    def get_selected_profile(self):
        """Retorna o perfil selecionado"""
        if self.selected_profile:
            # Verificar se é uma ação especial (string)
            if isinstance(self.selected_profile, str):
                if self.selected_profile == '__ADD_ADULT__':
                    pass
                elif self.selected_profile == '__ADD_KID__':
                    pass
                elif self.selected_profile == '__MANAGE__':
                    pass
                else:
                    pass
            # É um dict (perfil real)
            else:
                pass
        else:
            pass
        
        return self.selected_profile


# === HELPER FUNCTIONS ===

def show_profile_selector(addon_path, profiles):
    """
    Exibe o dialog de seleção de perfis
    
    Args:
        addon_path: Caminho do addon
        profiles: Lista de perfis
    
    Returns:
        Perfil selecionado, '__ADD_ADULT__', '__ADD_KID__', '__MANAGE__' ou None
    """
    dialog = DialogSelectProfile(
        'SelectProfile.xml',
        addon_path,
        profiles=profiles,
        addon_path=addon_path
    )
    
    dialog.doModal()
    selected = dialog.get_selected_profile()
    
    del dialog
    
    return selected