package com.captions.android.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun SettingsPage(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        content()
    }
}

@Composable
internal fun SettingGroup(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        content()
    }
}

@Composable
internal fun <T> ChoiceRow(
    choices: List<Pair<T, String>>,
    selected: T,
    onSelected: (T) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        choices.forEach { (value, label) ->
            val isSelected = value == selected
            TextButton(
                onClick = { onSelected(value) },
                modifier = Modifier.background(
                    color = if (isSelected) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        Color.Transparent
                    },
                    shape = MaterialTheme.shapes.large,
                ),
            ) {
                Text(
                    text = label,
                    color = if (isSelected) {
                        MaterialTheme.colorScheme.onPrimaryContainer
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
    }
}

@Composable
internal fun SizeSetting(label: String, value: Int, onChanged: (Int) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Spacer(Modifier.weight(1f))
        IconButton(onClick = { onChanged(value - 1) }) {
            Text("−", fontSize = 21.sp)
        }
        Text(
            text = value.toString(),
            fontSize = 15.sp,
            modifier = Modifier.widthIn(min = 28.dp),
        )
        IconButton(onClick = { onChanged(value + 1) }) {
            Text("+", fontSize = 19.sp)
        }
    }
}
