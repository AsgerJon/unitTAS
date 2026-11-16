package io.github.asgerjon.unittas.mixins.fabric;

import com.mojang.brigadier.suggestion.Suggestion;
import net.minecraft.client.gui.components.CommandSuggestions;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;

/** The suggestion list the chat shows: its suggestions, and the text it was made for (kept while Tab cycles them). */
@Mixin(CommandSuggestions.SuggestionsList.class)
public interface SuggestionsListAccess {

	@Accessor("originalContents")
	String unittas$madeFor();

	@Accessor("suggestionList")
	List<Suggestion> unittas$list();
}
